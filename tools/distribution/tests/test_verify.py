from unittest.mock import AsyncMock, PropertyMock

import pytest

from tools.base.checker import Checker
from tools.distribution import verify


def test_distrotest_constructor(patches):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    patched = patches(
        ("checker.Checker.stdout", dict(new_callable=PropertyMock)),
        ("DistroChecker.docker", dict(new_callable=PropertyMock)),
        ("DistroChecker.log", dict(new_callable=PropertyMock)),
        ("DistroChecker.testfile", dict(new_callable=PropertyMock)),
        prefix="tools.distribution.verify")

    with patched as (m_out, m_docker, m_log, m_test):
        assert dtest.checker == checker
        assert dtest.stdout == m_out.return_value
        assert dtest.docker == m_docker.return_value
        assert dtest.log == m_log.return_value
        assert dtest.testfile == m_test.return_value
        assert dtest.path == "PATH"
        assert dtest.installable == "INSTALLABLE"
        assert dtest.distro == "NAME"
        assert dtest.build_image == "IMAGE"
        assert dtest.build_tag == "TAG"


def test_distrotest_config(patches):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    assert dtest.config == dict(Image="NAME")


def test_distrotest_package_filename(patches):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    patched = patches(
        "os",
        prefix="tools.distribution.verify")

    with patched as (m_os,):
        assert dtest.package_filename == m_os.path.basename.return_value

    assert (
        list(m_os.path.basename.call_args)
        == [('INSTALLABLE',), {}])


def test_distrotest_package_name(patches):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    patched = patches(
        ("DistroTest.package_filename", dict(new_callable=PropertyMock)),
        prefix="tools.distribution.verify")

    with patched as (m_name,):
        assert dtest.package_name == m_name.return_value.split.return_value.__getitem__.return_value

    assert (
        list(m_name.return_value.split.call_args)
        == [('_',), {}])
    assert (
        list(m_name.return_value.split.return_value.__getitem__.call_args)
        == [(0,), {}])


def test_distrotest_mount_package_dir(patches):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    patched = patches(
        ("DistroTest.package_filename", dict(new_callable=PropertyMock)),
        prefix="tools.distribution.verify")

    with patched as (m_name, ):
        assert dtest.mount_package_dir == f"/tmp/install/{m_name.return_value}"


def test_distrotest_tag(patches):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    assert dtest.tag == "NAME:latest"


def test_distrotest_test_cmd(patches):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    patched = patches(
        ("DistroTest.mount_package_dir", dict(new_callable=PropertyMock)),
        ("DistroTest.package_name", dict(new_callable=PropertyMock)),
        ("DistroTest.mount_testfile_path", dict(new_callable=PropertyMock)),
        prefix="tools.distribution.verify")

    with patched as (m_ppath, m_name, m_tpath):
        assert dtest.test_cmd == (
            m_tpath.return_value,
            m_ppath.return_value,
            m_name.return_value,
            "NAME")


@pytest.mark.asyncio
@pytest.mark.parametrize("exists", [True, False])
async def test_distrotest_build(patches, exists):
    checker = verify.DistroChecker()
    dtest = verify.DistroTest(checker, "PATH", "INSTALLABLE", "NAME", "IMAGE", "TAG")
    patched = patches(
        ("DistroTest.docker_build", dict(new_callable=AsyncMock)),
        ("DistroTest.image_exists", dict(new_callable=AsyncMock)),
        ("DistroTest.log", dict(new_callable=PropertyMock)),
        prefix="tools.distribution.verify")

    with patched as (m_build, m_exists, m_log):
        m_exists.return_value = exists
        assert not await dtest.build()

    assert (
        list(m_exists.call_args)
        == [(), {}])

    if exists:
        assert not m_log.called
        assert not m_build.called
        return

    assert (
        list(m_build.call_args)
        == [(), {}])
    assert (
        list(list(c) for c in m_log.return_value.info.call_args)
        == [['[NAME] Image built'], []])


def test_checker_constructor(patches):
    checker = verify.DistroChecker("path1", "path2", "path3")
    assert isinstance(checker, Checker)

    patched = patches(
        ("DistroChecker.args", dict(new_callable=PropertyMock)),
        prefix="tools.distribution.verify")

    with patched as (m_args, ):
        assert checker.config == m_args.return_value.config
        assert checker.packages_tarball == m_args.return_value.packages
        assert checker.testfile == m_args.return_value.testfile
        assert checker.test_distributions == m_args.return_value.distribution
        assert checker.distro_test_class == verify.DistroTest


def test_checker_docker(patches):
    checker = verify.DistroChecker("path1", "path2", "path3")
    patched = patches(
        "aiodocker",
        prefix="tools.distribution.verify")

    with patched as (m_docker, ):
        assert checker.docker == m_docker.Docker.return_value

    assert (
        list(m_docker.Docker.call_args)
        == [(), {}])
    assert "docker" in checker.__dict__


def test_checker_tempdir(patches):
    checker = verify.DistroChecker("path1", "path2", "path3")
    patched = patches(
        "tempfile",
        prefix="tools.distribution.verify")

    with patched as (m_temp, ):
        assert checker.tempdir == m_temp.TemporaryDirectory.return_value

    assert (
        list(m_temp.TemporaryDirectory.call_args)
        == [(), {}])
    assert "tempdir" in checker.__dict__
