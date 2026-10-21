from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class WindowsInstallLayoutTests(unittest.TestCase):
    def test_windows_installer_requires_admin_and_targets_program_files(self) -> None:
        installer = _text("installer/CRAFT.iss")

        self.assertIn("PrivilegesRequired=admin", installer)
        self.assertIn(r"DefaultDirName={autopf}\XRD Craft", installer)
        self.assertIn(r'Name: "{commonappdata}\Sci"; Permissions: users-modify', installer)
        self.assertIn(
            r'Filename: "{cmd}"; Parameters: "/D /C ""{app}\toolkit\setup_sci_env.bat"""',
            installer,
        )
        self.assertNotIn("runascurrentuser", installer)

    def test_windows_launch_and_setup_share_programdata_sci_environment(self) -> None:
        launcher = _text("run_craft.bat")
        setup = _text("toolkit/setup_sci_env.bat")

        self.assertIn(r'set "SCI_PYTHON=%PROGRAMDATA%\Sci\env\Scripts\pythonw.exe"', launcher)
        self.assertIn(r'set "SCI_ROOT=%PROGRAMDATA%\Sci"', setup)
        self.assertNotIn(r"%LOCALAPPDATA%\Sci", launcher)
        self.assertNotIn(r"%LOCALAPPDATA%\Sci", setup)

    def test_windows_installer_and_shortcuts_use_craft_icon(self) -> None:
        installer = _text("installer/CRAFT.iss")

        self.assertIn(r"SetupIconFile=..\assets\craft.ico", installer)
        self.assertIn(r"UninstallDisplayIcon={app}\assets\craft.ico", installer)
        self.assertGreaterEqual(installer.count(r'IconFilename: "{app}\assets\craft.ico"'), 2)

    def test_windows_installer_always_creates_common_desktop_shortcut(self) -> None:
        installer = _text("installer/CRAFT.iss")

        self.assertIn(
            r'Name: "{commondesktop}\CRAFT"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_craft_silent.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\craft.ico"',
            installer,
        )
        self.assertNotIn("desktopicon", installer)

    def test_windows_release_metadata_and_download_documentation_are_1_1_2(self) -> None:
        installer = _text("installer/CRAFT.iss")
        project = _text("pyproject.toml")
        package = _text("craft/__init__.py")
        readme = _text("README.md")

        self.assertIn('#define MyAppVersion "1.1.2"', installer)
        self.assertIn("OutputBaseFilename=CRAFT_Windows_{#MyAppVersion}_Setup", installer)
        self.assertIn('version = "1.1.2"', project)
        self.assertIn('__version__ = "1.1.2"', package)
        self.assertIn("CRAFT_Windows_1.1.2_Setup.exe", readme)
        self.assertIn("Program Files", readme)
        self.assertIn("ProgramData", readme)


if __name__ == "__main__":
    unittest.main()
