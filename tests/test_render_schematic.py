import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

from scripts.render_schematic import render


class RenderSchematicTests(unittest.TestCase):
    def test_exports_and_validates_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schematic = root / "design.kicad_sch"
            schematic.write_text("(kicad_sch)", encoding="utf-8")
            output = root / "images"

            def fake_run(command, **kwargs):
                output.mkdir(parents=True, exist_ok=True)
                (output / "design.svg").write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8"
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("scripts.render_schematic.subprocess.run", side_effect=fake_run):
                files = render(schematic, output)

            self.assertEqual([output / "design.svg"], files)

    def test_missing_cli_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schematic = root / "design.kicad_sch"
            schematic.write_text("(kicad_sch)", encoding="utf-8")
            with patch(
                "scripts.render_schematic.subprocess.run",
                side_effect=FileNotFoundError("missing"),
            ):
                with self.assertRaisesRegex(RuntimeError, "install KiCad 9"):
                    render(schematic, root / "images")

    def test_rejects_success_without_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schematic = root / "design.kicad_sch"
            schematic.write_text("(kicad_sch)", encoding="utf-8")
            with patch(
                "scripts.render_schematic.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ):
                with self.assertRaisesRegex(RuntimeError, "no SVG"):
                    render(schematic, root / "images")


if __name__ == "__main__":
    unittest.main()
