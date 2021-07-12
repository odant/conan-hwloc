from conans import ConanFile, MSBuild, tools
import os, glob

class ICUConan(ConanFile):
    name = "hwloc"
    version = "2.5.0+0"
    license = "https://www.open-mpi.org/projects/hwloc/license.php"
    description = "The Portable Hardware Locality (hwloc) software package provides a portable abstraction (across OS, versions, architectures, ...) of the hierarchical topology of modern architectures, including NUMA memory nodes, sockets, shared caches, cores and simultaneous multithreading. It also gathers various system attributes such as cache and memory information as well as the locality of I/O devices such as network interfaces, InfiniBand HCAs or GPUs."
    url = "https://www.open-mpi.org/projects/hwloc/"
    settings = {
        "os": ["Windows", "Linux"],
        "compiler": ["Visual Studio", "gcc", "clang"],
        "build_type": ["Debug", "Release"],
        "arch": ["x86", "x86_64", "mips", "armv7"]
    }
    options = {
        "dll_sign": [True, False],
        "shared": [True, False]
    }
    default_options = {
        "dll_sign": True,
        "shared": True
    }
    exports_sources = "src/*", "LICENSE", "add_msvc_win32.patch"
    no_copy_source = False
    build_policy = "missing"

    def configure(self):
        # Only C++11
        if self.settings.compiler.get_safe("libcxx") == "libstdc++":
            raise Exception("This package is only compatible with libstdc++11")
        # MT(d) static library
        if self.settings.os == "Windows" and self.settings.compiler == "Visual Studio":
            if self.settings.compiler.runtime == "MT" or self.settings.compiler.runtime == "MTd":
                self.options.shared = False
        # DLL sign, only Windows and shared
        if self.settings.os != "Windows" or self.options.shared == False:
            self.options.dll_sign = False

    def build_requirements(self):
        if self.options.get_safe("dll_sign"):
            self.build_requires("windows_signtool/[>=1.2]@%s/stable" % self.user)

    def source(self):
        if tools.os_info.is_windows:
            tools.patch(patch_file="add_msvc_win32.patch")
        else:
            self.run("chmod a+x %s" % os.path.join(self.source_folder, "src/configure"))

    def build(self):
        if self.settings.compiler == "Visual Studio":
            self.msvc_build()
        else:
            self.unix_build()
            
    def unix_build(self):
        flags = self.get_build_flags()
        install_folder = os.path.join(self.build_folder, "hwloc_install").replace("\\", "/")
        flags.append("--prefix=%s" % tools.unix_path(install_folder))
        build_env = self.get_build_environment()
        with tools.chdir("src"), tools.environment_append(build_env):
            self.run("./configure %s" % " ".join(flags))
            debug_arg = "" #"VERBOSE=1" if self.settings.build_type == "Debug" else ""
            self.run("make %s -j %s" % (debug_arg, tools.cpu_count()))
            self.run("make install")

    def msvc_build(self):
        if self.settings.build_type == "Debug":
            self.msvc_build_type = "DebugDll" if self.options.shared else "DebugStatic"
        else:
            self.msvc_build_type = "Release" if self.options.shared else "ReleaseStatic"
        self.msvc_arch  = "x64" if self.settings.arch == "x86_64" else "Win32"        
        with tools.chdir("src/contrib/windows"):
            builder = MSBuild(self)
            builder.build("libhwloc.vcxproj", build_type=self.msvc_build_type, upgrade_project=False, verbosity="normal", use_env=False, platforms={"x86":"Win32"})
            
    def get_build_flags(self):
        flags = []
        if self.settings.build_type == "Debug":
            flags.extend([
                "--enable-debug",
                "--disable-release"
            ])
        #flags.append(self.get_target_platform())
        if self.options.shared:
            flags.extend([
                "--enable-shared",
                "--disable-static"
            ])
        else:
            flags.extend([
                "--disable-shared",
                "--enable-static",
            ])
        flags.extend([
            "--disable-libxml2"
        ])
        return flags

    def get_target_platform(self):
        if self.settings.os == "Windows" and self.settings.compiler == "Visual Studio":
            platform = "Cygwin/MSVC"
            vs_toolset = str(self.settings.compiler.toolset).lower()
            if vs_toolset == "clangcl":
                platform += "_ClangCL"
            if self.settings.compiler.runtime == "MT" or self.settings.compiler.runtime == "MTd":
                platform += "_MT"
            self.output.info("Using '%s' target platform" % platform)
            return platform
        elif self.settings.os == "Linux":
            if self.settings.compiler == "gcc":
                return "Linux/gcc"
            else:
                return "Linux" # Use the clang/clang++ or GNU gcc/g++ compilers on Linux
        else:
            raise Exception("Unsupported target platform!")

    def get_build_environment(self):
        env = {}
        if self.settings.os == "Windows" and self.settings.compiler == "Visual Studio":
            env = tools.vcvars_dict(self)
        return env

    def package(self):
        if self.settings.compiler == "Visual Studio":
            self.msvc_package()
        else:
            self.unix_package()
    
    def unix_package(self):
        # CMake script
        #self.copy("FindICU.cmake", dst=".", src=".", keep_path=False)
        # Headers
        self.copy("*", dst="include", src="hwloc_install/include", keep_path=True)
        # Linux libraries
        self.copy("*", dst="lib", src="hwloc_install/lib", keep_path=True, symlinks=True)

        # Debug build in local folder
        if not self.in_local_cache:
            self.copy("conanfile.py", dst=".", keep_path=False)
    
    def msvc_package(self):
        # CMake script
        #self.copy("FindICU.cmake", dst=".", src=".", keep_path=False)
        # Headers
        self.copy("hwloc.h", dst="include", src="src/include", keep_path=False)
        self.copy("*", dst="include/hwloc", src="src/include/hwloc", keep_path=True)
        # Windows libraries
        build_folder = ("src/contrib/windows/%s/%s" % (self.msvc_arch, self.msvc_build_type))
        self.copy("lib*.dll", dst="bin", src=build_folder, keep_path=False)
        self.copy("lib*.pdb", dst="bin", src=build_folder, keep_path=False)
        self.copy("lib*.lib", dst="lib", src=build_folder, keep_path=False)
        # Sign DLL
        if self.options.get_safe("dll_sign"):
            import windows_signtool
            pattern = os.path.join(self.package_folder, "bin", "*.dll")
            for fpath in glob.glob(pattern):
                fpath = fpath.replace("\\", "/")
                for alg in ["sha1", "sha256"]:
                    is_timestamp = True if self.settings.build_type == "Release" else False
                    cmd = windows_signtool.get_sign_command(fpath, digest_algorithm=alg, timestamp=is_timestamp)
                    self.output.info("Sign %s" % fpath)
                    self.run(cmd)

    def package_info(self):
        self.cpp_info.libs = tools.collect_libs(self)
