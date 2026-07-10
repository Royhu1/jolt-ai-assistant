"""把 HTML 模板渲染为 PDF —— 使用本机已安装的 headless Chrome / Edge。

设计取舍见同目录 ``SKILL.md``：在 Windows 上 Chromium 系内核
（Chrome 或 Edge）的 ``--print-to-pdf`` 提供最高保真度且零额外依赖
（无需 WeasyPrint 的 GTK、也无需 Playwright）。HTML 模板文末的测高脚本会在
load 后注入命名 ``@page`` 尺寸，使 PDF 每页 = 浏览器预览的内容自适应高度
（PDF 与 HTML 预览一致）。

用法（从仓库根运行）：
    python .claude/skills/generate-pdf-report/build_pdf.py --html <输入.html> --out <输出.pdf>

生成产物默认写到 ``pdf_report_workspace/output_by_TBD/``（工作区，定稿后改名为 output_by_<YYYYMMDD>；已在 .gitignore 中忽略）。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]  # repo root (script lives at .claude/skills/generate-pdf-report/)
DEFAULT_OUT = PROJECT / "pdf_report_workspace" / "output" / "report_sample.pdf"

# 常见的 Chromium 系内核安装位置（按优先级）
CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    """返回可用的 Chromium 系浏览器可执行文件路径。"""
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe"):
        found = shutil.which(name)
        if found:
            return found
    for path in CANDIDATES:
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        "未找到 Chrome 或 Edge。请安装 Chromium 系浏览器，或用 --browser 指定路径。"
    )


def html_to_pdf(html: Path, out: Path, browser: str | None = None) -> Path:
    """用 headless Chrome/Edge 把 *html* 打印为 *out* PDF。"""
    browser = browser or find_browser()
    out.parent.mkdir(parents=True, exist_ok=True)
    # 先删旧 PDF：渲染失败时 out 不存在会报错，而非静默沿用旧文件。
    # 若旧文件被占用（常见于已在 PDF 阅读器中打开）→ 改写到带时间戳的新名字。
    try:
        out.unlink(missing_ok=True)
    except PermissionError:
        out = out.with_name(f"{out.stem}_{int(time.time())}{out.suffix}")
        print(f"[build_pdf] 原 PDF 被占用（可能正在阅读器中打开），改写到：{out.name}")
    url = html.resolve().as_uri()  # file:///... 形式，Chrome 可读本地资源

    print(f"[build_pdf] browser : {browser}")
    print(f"[build_pdf] input   : {html}")
    print(f"[build_pdf] output  : {out}")
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",       # 去掉默认的日期 / URL 页眉页脚
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={out.resolve()}",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out.exists():
        sys.stderr.write(result.stdout + "\n" + result.stderr + "\n")
        raise RuntimeError(f"渲染失败（exit={result.returncode}）")
    print(f"[build_pdf] done    : {out} ({out.stat().st_size/1024:.0f} KB)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="HTML → PDF（headless Chrome/Edge）。"
                                 "通常由 generate_report.py 调用；此 CLI 仅作通用 HTML→PDF 工具。")
    ap.add_argument("--html", type=Path, required=True, help="输入 HTML 路径")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出 PDF 路径")
    ap.add_argument("--browser", type=str, default=None, help="浏览器可执行文件路径（可选）")
    args = ap.parse_args()
    html_to_pdf(args.html, args.out, args.browser)


if __name__ == "__main__":
    main()
