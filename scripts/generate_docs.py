#!/usr/bin/env python3
"""
Generate documentation in various formats.

Usage:
    python scripts/generate_docs.py          # Generate all docs
    python scripts/generate_docs.py --pdf    # Generate PDF only
    python scripts/generate_docs.py --html   # Generate HTML only
"""

import subprocess
import sys
from pathlib import Path


def generate_pdf(input_path: Path, output_path: Path) -> bool:
    """Generate PDF from Markdown using pandoc."""
    try:
        cmd = [
            "pandoc",
            str(input_path),
            "-o", str(output_path),
            "--pdf-engine=xelatex",
            "-V", "geometry:margin=1in",
            "-V", "fontsize=11pt",
            "--toc",
            "--toc-depth=3",
            "-V", "colorlinks=true",
            "-V", "linkcolor=blue"
        ]
        subprocess.run(cmd, check=True)
        print(f"Generated PDF: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error generating PDF: {e}")
        return False
    except FileNotFoundError:
        print("pandoc not found. Install with: sudo apt install pandoc texlive-xetex")
        return False


def generate_html(input_path: Path, output_path: Path) -> bool:
    """Generate HTML from Markdown."""
    try:
        cmd = [
            "pandoc",
            str(input_path),
            "-o", str(output_path),
            "--standalone",
            "--toc",
            "--toc-depth=3",
            "-c", "https://cdn.jsdelivr.net/npm/water.css@2/out/dark.min.css"
        ]
        subprocess.run(cmd, check=True)
        print(f"Generated HTML: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error generating HTML: {e}")
        return False
    except FileNotFoundError:
        print("pandoc not found. Install with: sudo apt install pandoc")
        return False


def main():
    """Main function."""
    docs_dir = Path(__file__).parent.parent / "docs"
    deployment_guide = docs_dir / "DEPLOYMENT_GUIDE.md"

    if not deployment_guide.exists():
        print(f"Error: {deployment_guide} not found")
        sys.exit(1)

    # Parse arguments
    generate_all = len(sys.argv) == 1
    gen_pdf = "--pdf" in sys.argv or generate_all
    gen_html = "--html" in sys.argv or generate_all

    success = True

    if gen_pdf:
        pdf_path = docs_dir / "Revolution_Alpha_Engine_Manual.pdf"
        if not generate_pdf(deployment_guide, pdf_path):
            success = False

    if gen_html:
        html_path = docs_dir / "manual.html"
        if not generate_html(deployment_guide, html_path):
            success = False

    if success:
        print("\nDocumentation generated successfully!")
    else:
        print("\nSome documentation failed to generate. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
