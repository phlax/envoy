import argparse
import itertools
import logging
import os
import shutil
import sys
import tarfile
import tempfile
from functools import cached_property
from typing import Iterable, Optional, Tuple, Type, Union

import verboselogs

import yaml

import aiodocker

from tools.base import checker
from tools.docker import utils as docker_utils

DEB_BUILD_COMMAND = (
    "chmod +x /tmp/distrotest.sh "
    "&& apt-get update "
    "&& apt-get install -y -qq --no-install-recommends curl procps sudo")
DEB_BUILD_ENV = "ENV DEBIAN_FRONTEND=noninteractive"

DOCKERFILE_TEMPLATE = """
FROM {distro}:{tag}
{env}

ADD {install_dir} {install_mount_path}
ADD {test_filename} {test_mount_path}
RUN {build_command}

CMD ["tail", "-f", "/dev/null"]
"""

# CMD ["echo", "EXITING"]

RPM_BUILD_COMMAND = (
    "chmod +x /tmp/distrotest.sh "
    "&& yum -y install procps sudo")


class BuildError(Exception):
    pass


class ContainerError(Exception):
    pass


class DistroTest(object):
    """A distribution <> package test

    Supplied `path` is the path to a (temporary) directory containing a
    `Dockerfile` and any artefacts required to build the distribution to test.

    The image is only built if it does not exist already.

    `installable` is the path to the package to test.

    The test starts the distro test container, and then `execs` the test script
    inside to run the actual tests.
    """

    def __init__(self, checker: "DistroChecker", path: str, installable: str, name: str, image: str, tag: str):
        self.checker = checker
        self.path = path
        self.installable = installable
        self.distro = name
        self.build_image = image
        self.build_tag = tag

    @property
    def build_testfile_path(self) -> str:
        return os.path.join(self.path, os.path.basename(self.testfile))

    @property
    def config(self) -> dict:
        """Docker container config"""
        # todo as autoremove doesnt quite work, add container removal or fix
        # HostConfig=dict(AutoRemove=True))
        return dict(Image=self.distro)

    @property
    def docker(self) -> aiodocker.Docker:
        """aiodocker.Docker connection"""
        return self.checker.docker

    @cached_property
    def dockerfile(self) -> str:
        return self.dockerfile_template.format(
            distro=self.build_image,
            tag=self.build_tag,
            install_dir=self.install_dir,
            env=self.build_env,
            install_mount_path=self.mount_install_dir,
            test_filename=self.testfile_name,
            test_mount_path=self.mount_testfile_path,
            build_command=self.build_command)

    @property
    def dockerfile_template(self):
        return DOCKERFILE_TEMPLATE

    @property
    def environment(self) -> dict:
        """Docker exec environment for the test"""
        return {}

    @property
    def log(self) -> verboselogs.VerboseLogger:
        """A Logger to send progress information to"""
        return self.checker.log

    @property
    def mount_install_dir(self) -> str:
        return "/tmp/install"

    @property
    def mount_package_dir(self) -> str:
        """Path to the package inside the container"""
        # as this is a path inside the linux container - dont use `os`
        return f"{self.mount_install_dir}/{self.package_filename}"

    @property
    def mount_testfile_path(self) -> str:
        """Path to the testfile inside the test container"""
        # as this is a path inside the linux container - dont use `os`
        return f"/tmp/{self.testfile_name}"

    @cached_property
    def name(self) -> str:
        """The name of the Docker container used to test"""
        return "testing"

    @cached_property
    def package_filename(self) -> str:
        """The package filename"""
        return os.path.basename(self.installable)

    @cached_property
    def package_name(self) -> str:
        """The name of the package derived from the filename - eg `envoy-1.19`"""
        return self.package_filename.split("_")[0]

    @property
    def stdout(self) -> logging.Logger:
        """A Logger for raw logging"""
        return self.checker.stdout

    @cached_property
    def tag(self) -> str:
        """Tag for the Docker test image build"""
        return f"{self.distro}:latest"

    @property
    def test_cmd(self) -> tuple:
        """The test command to run inside the test container"""
        return (
            self.mount_testfile_path,
            self.mount_package_dir,
            self.package_name,
            self.distro)

    @property
    def testfile(self) -> str:
        """Path to the testfile"""
        return self.checker.testfile

    @property
    def testfile_name(self) -> str:
        """Path to the testfile"""
        return os.path.basename(self.testfile)

    def add_artefacts(self) -> None:
        """Add artefacts required to build the Docker test image"""

        with open(os.path.join(self.path, "Dockerfile"), "w") as f:
            self.stdout.info(self.dockerfile)
            f.write(self.dockerfile)

        # add the testfile - distrotest.sh
        shutil.copyfile(self.testfile, self.build_testfile_path)

    async def build(self) -> None:
        """Build the Docker image for the test with required artefacts"""
        if await self.image_exists():
            return
        await self.docker_build()
        self.run_log("Image built")

    async def cleanup(self) -> None:
        """Attempt to kill the test container.

        As this is cleanup code, run when system is exiting, *ignore all errors*.
        """
        try:
            await self.stop(await self.docker.containers.get(self.name))
        finally:
            return

    async def create(self) -> aiodocker.containers.DockerContainer:
        """Create a Docker container for the test"""
        return await self.docker.containers.create_or_replace(config=self.config, name=self.name)

    async def docker_build(self) -> None:
        """Add the required artefacts and build the Docker image for the test"""
        self.checker.log.notice(self.run_message("Building image"))
        self.add_artefacts()
        try:
            await docker_utils.build_image(
                self.docker,
                self.path,
                self.tag,
                stream=self.stdout.info,
                forcerm=True)
        except docker_utils.BuildError as e:
            raise BuildError(e.args[0])

    async def docker_images(self) -> Iterable[str]:
        """The currently built Docker image tag names"""
        return itertools.chain.from_iterable(
            [image["RepoTags"] for image in await self.docker.images.list()])

    async def exec(self, container: aiodocker.containers.DockerContainer) -> int:
        """Run Docker `exec` with the test"""
        execute = await container.exec(self.test_cmd, environment=self.environment)

        async with execute.start(detach=False) as stream:
            msg = await stream.read_out()
            _out = ""
            while msg:
                if _out:
                    self.handle_test_output(_out)
                _out = msg.data.decode("utf-8").strip()
                msg = await stream.read_out()

        return_code = (await execute.inspect())["ExitCode"]
        # this is not quite right yet...
        # the reason for using `_out` is to catch the situation where it outputs
        # one log and then fails - in that case we want to catch and log and not
        # just send it to stdout
        if _out:
            if return_code:
                # the test hasnt begun - log the error
                if not self.checker.exiting and not "distros" in self.checker.errors:
                    self.error([f"[{self.distro}] Error executing test in container\n{_out}"])
            else:
                self.handle_test_output(_out)

        return return_code

    def error(self, errors: Union[list, tuple]) -> int:
        """Fail a test and log the errors"""
        return self.checker.error("distros", errors)

    def handle_test_output(self, msg: str) -> None:
        """Handle and log stream from test container

        if the message startswith eg `[debian_buster/envoy-19` then treat the
        message as a control message, otherwise log directly to stdout.

        if a control message contains `ERROR` then its treated as an error,
        and the test is marked as failed
        """

        if not msg.startswith(f"[{self.distro}"):
            # raw log
            self.stdout.info(msg)
            return

        if "ERROR" not in msg:
            # log informational message
            self.log.info(msg)
            return

        # testrun is eg `debian_buster/envoy-1.19`
        # testname is eg `proxy-responds`
        testrun, testname = msg.split("]")[0].strip("[").split(":")

        # fail the test, log an error, and output any extra `msg` content as
        # raw logs
        self.error([f"[{testrun}:{testname}] Test failed"])
        _msg = msg.split("\n", 1)
        if len(_msg) > 1:
            self.checker.stdout.error(_msg[1])

    async def image_exists(self) -> bool:
        """Check if the Docker image exists already for the distribution"""
        return self.tag in await self.docker_images()

    def log_failures(self) -> None:
        failures = None
        if "distros" in self.checker.errors:
            # store/retrieve this internally
            failures = ",".join([
                fail.split("]")[0].strip("[").split(":")[1]
                for fail in self.checker.errors["distros"]
                if fail.startswith(f"[{self.distro}/{self.package_name}:")])

        if failures:
            self.checker.log.error(self.run_message(f"Package test had failures: {failures}", test=self.package_name))
        else:
            self.checker.log.success(self.run_message(f"Package test passed", test=self.package_name))

    async def logs(self, container: aiodocker.containers.DockerContainer) -> str:
        return ''.join(log for log in await container.log(stdout=True, stderr=True))

    async def on_test_complete(self, container: aiodocker.containers.DockerContainer) -> Optional[Tuple[str]]:
        errors = await self.stop(container)
        if not self.checker.exiting:
            self.log_failures()
        return errors

    async def run(self) -> Optional[Tuple[str]]:
        """Run the test"""
        container = None
        try:
            await self.build()
            container = await self.start()
        except aiodocker.exceptions.DockerError as e:
            return (e.args[1]["message"],)
        except (BuildError, ContainerError) as e:
            return e.args
        else:
            try:
                await self.exec(container)
            except aiodocker.exceptions.DockerError as e:
                return (e.args[1]["message"],)
        finally:
            return await self.on_test_complete(container)

    def run_log(self, message: str, test: Optional[str] = None) -> None:
        self.log.info(self.run_message(message, test=test))

    def run_message(self, message: str, test: Optional[str] = None) -> None:
        return (f"[{self.distro}/{test}] {message}" if test else f"[{self.distro}] {message}")

    async def start(self) -> aiodocker.containers.DockerContainer:
        container = await self.create()
        await container.start()
        info = await container.show()
        if not info["State"]["Running"]:
            raise ContainerError(
                self.run_message(
                    f"Container unable to start\n{await self.logs(container)}", test=self.package_name))
        self.run_log("Container started", test=self.package_name)
        return container

    async def stop(
            self,
            container: Optional[aiodocker.containers.DockerContainer] = None) -> Optional[tuple]:
        """Stop the test container catching and returning any errors"""
        if not container:
            return
        try:
            await container.kill()
            await container.wait()
            await container.delete(force=True)
        except aiodocker.exceptions.DockerError as e:
            return (e.args[1]["message"],)
        self.run_log("Container stopped", test=self.package_name)


class DebDistroTest(DistroTest):

    @property
    def build_command(self) -> str:
        return DEB_BUILD_COMMAND

    @property
    def build_env(self) -> str:
        return DEB_BUILD_ENV

    @property
    def environment(self) -> dict:
        return dict(
            INSTALL_COMMAND="apt-get install -yy -q ",
            UNINSTALL_COMMAND="apt-get remove --purge -y -qq",
            MAINTAINER_COMMAND="apt show")

    @property
    def install_dir(self) -> str:
        return "packages/deb"


class RPMDistroTest(DistroTest):

    @property
    def build_command(self) -> str:
        return RPM_BUILD_COMMAND

    @property
    def build_env(self) -> str:
        return ""

    @property
    def environment(self) -> dict:
        return dict(
            INSTALL_COMMAND="rpm -i --force",
            UNINSTALL_COMMAND="rpm -e",
            MAINTAINER_COMMAND="rpm -qi")

    @property
    def install_dir(self) -> str:
        return "packages/rpm"


class DistroChecker(checker.AsyncChecker):
    _active_test = None
    checks = ("distros",)

    _test_types = ()

    @classmethod
    def register_test(cls, name: str, util: Type[DistroTest]) -> None:
        """Register util for signing a package type"""
        cls._test_types = getattr(cls, "_test_types") + ((name, util),)

    @property
    def active_test(self) -> Optional[DistroTest]:
        return self._active_test

    @property
    def config(self) -> str:
        return self.args.config

    @property
    def distro_test_class(self) -> Type[DistroTest]:
        return DistroTest

    @cached_property
    def distros(self) -> list:
        with open(self.config) as f:
            return yaml.safe_load(f.read())

    @cached_property
    def docker(self) -> aiodocker.Docker:
        return aiodocker.Docker()

    @cached_property
    def packages_dir(self) -> str:
        packages_dir = os.path.join(self.tempdir.name, "packages")
        self.extract(self.packages_tarball, packages_dir)
        return packages_dir

    @property
    def packages_tarball(self) -> str:
        return self.args.packages

    @cached_property
    def tempdir(self) -> tempfile.TemporaryDirectory:
        """A temporary directory with a package set and a distribution set extracted"""
        return tempfile.TemporaryDirectory()

    @property
    def testfile(self) -> str:
        return self.args.testfile

    @property
    def test_distributions(self) -> str:
        return self.args.distribution

    @cached_property
    def test_types(self) -> dict:
         return dict(getattr(self, "_test_types"))

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "testfile",
            help="Path to the test file that will be run inside the distribution containers")
        parser.add_argument(
            "config",
            help="Path to a YAML configuration with distributions for testing")
        parser.add_argument("packages", help="Path to a tarball containing packages to test")
        parser.add_argument(
            "--distribution",
            "-d",
            nargs="?",
            help="Specify distribution to test. Can be specified multiple times.")

    async def check_distros(self) -> None:
        for distro in self.distros:
            if not self.test_distributions or distro in self.test_distributions:
                self.log.info(f"[{distro}] Testing with: " f"{self.pkg_names(distro)}")
                errors = await self.distro_test(distro, **self.distros[distro])

    async def distro_test(self, distro: str, image: str, tag: str) -> tuple:
        """Runs a test for each of the packages against a particular distro"""
        errors = ()
        for installable in self.pkg_paths(distro):
            if self.exiting:
                return errors
            self.log.info(f"[{distro}] Testing package: {installable}")
            self._active_test = self.test_types[self.pkg_type(distro)](
                self, self.tempdir.name, installable, distro, image, tag)
            await self._active_test.run() or ()
        return errors

    def extract(self, tarball: str, path: str) -> None:
        with tarfile.open(tarball) as tar:
            tar.extractall(path=path)

    async def on_checks_complete(self) -> int:
        await self._cleanup_test()
        await self._cleanup_docker()
        await self._cleanup_tempdir()
        return await super().on_checks_complete()

    def pkg_names(self, distro: str) -> str:
        """Packages found for a particular distro type - ie debs/rpms"""
        return " ".join(os.path.basename(pkg).split("_")[0] for pkg in self.pkg_paths(distro))

    def pkg_path(self, pkg_type: str, pkg: Optional[str] = None) -> str:
        args = [self.packages_dir, pkg_type]
        if pkg:
            args.append(pkg)
        return os.path.join(*args)

    def pkg_paths(self, distro: str) -> list:
        """Packages found for a particular distro type - ie debs/rpms"""
        pkg_type = self.pkg_type(distro)
        return [
            self.pkg_path(pkg_type, pkg)
            for pkg in os.listdir(self.pkg_path(pkg_type))
            if pkg.endswith(pkg_type)
        ]

    def pkg_type(self, distro: str) -> str:
        return "deb" if distro.startswith("debian") or distro.startswith("ubuntu") else "rpm"

    async def _cleanup_docker(self) -> None:
        if "docker" in self.__dict__:
            await self.docker.close()
            del self.__dict__["docker"]

    async def _cleanup_tempdir(self) -> None:
        if "tempdir" in self.__dict__:
            self.tempdir.cleanup()
            del self.__dict__["tempdir"]

    async def _cleanup_test(self) -> None:
        if self.active_test:
            await self.active_test.cleanup()


def _register_utils() -> None:
    DistroChecker.register_test("deb", DebDistroTest)
    DistroChecker.register_test("rpm", RPMDistroTest)


def main(*args) -> int:
    _register_utils()
    return DistroChecker(*args).run()


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
