load("@rules_android//android:rules.bzl", "android_sdk_repository")
load("@rules_android_ndk//:rules.bzl", "android_ndk_repository")
load("//bazel:envoy_mobile_dependencies.bzl", "default_extra_jni_deps", "default_extra_swift_sources")
load("//bazel:platforms.bzl", "envoy_mobile_platforms")

def _mobile_platforms_impl(ctx):
    envoy_mobile_platforms()

envoy_mobile_platforms_extension = module_extension(
    implementation = _mobile_platforms_impl,
)

def _extra_sources_impl(_ctx):
    default_extra_swift_sources(name = "envoy_mobile_extra_swift_sources")
    default_extra_jni_deps(name = "envoy_mobile_extra_jni_deps")

envoy_mobile_extra_sources_extension = module_extension(implementation = _extra_sources_impl)

def _stub_impl(ctx):
    ctx.file("BUILD.bazel", "")

_stub_repo = repository_rule(implementation = _stub_impl)

def _ndk_impl(ctx):
    if ctx.getenv("ANDROID_NDK_HOME"):
        android_ndk_repository(name = "androidndk", api_level = 23)
    else:
        _stub_repo(name = "androidndk")

android_ndk_extension = module_extension(
    implementation = _ndk_impl,
    environ = ["ANDROID_NDK_HOME"],
)

def _sdk_impl(ctx):
    if ctx.os.environ.get("ANDROID_HOME"):
        android_sdk_repository(
            name = "androidsdk",
            api_level = 30,
            build_tools_version = "35.0.0",
        )
    else:
        _stub_repo(name = "androidsdk")

android_sdk_extension = module_extension(
    implementation = _sdk_impl,
    environ = ["ANDROID_HOME"],
)
