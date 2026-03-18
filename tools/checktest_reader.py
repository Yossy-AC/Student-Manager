#!/usr/bin/env python3
"""
checktest_reader.py — チェックテスト自動読み取りパイプライン（CLI）

Usage:
    python checktest_reader.py --pdf scan.pdf --config config/class_A.json
    python checktest_reader.py --pdf scan.pdf --config config/class_A.json --debug --pages 1
    python checktest_reader.py --pdf checktest_template.pdf --config config/class_sample.json --pages 4 --debug
"""

import argparse
import logging
import sys

from app.core.checktest.constants import DEFAULT_DPI, DEFAULT_MARK_THRESH
from app.core.checktest.excel_writer import write_excel
from app.core.checktest.processor import fail_result, load_config, process_page
from app.core.checktest.scanner import pdf_to_images

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="チェックテスト採点欄スキャン PDF を自動読み取りし Excel に出力する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # B4 横置きスキャン（通常）
  python checktest_reader.py --pdf input/scan.pdf --config config/class_A.json

  # テンプレート PDF でのテスト（ページ 4 のみ、portrait なので自動的にクロップなし）
  python checktest_reader.py --pdf checktest_template.pdf --config config/class_sample.json --pages 4 --debug

  # 閾値を調整してデバッグ
  python checktest_reader.py --pdf input/scan.pdf --config config/class_A.json --thresh 0.30 --debug --pages 1 2 3
""",
    )
    p.add_argument("--pdf",    required=True,  help="スキャン PDF のパス")
    p.add_argument("--config", required=True,  help="クラス設定 JSON のパス")
    p.add_argument("--out",    default="output/results.xlsx",
                   help="出力 Excel のパス（デフォルト: output/results.xlsx）")
    p.add_argument("--debug",  action="store_true", help="デバッグ画像を debug/ に出力する")
    p.add_argument("--thresh", type=float, default=DEFAULT_MARK_THRESH,
                   help=f"マーク判定閾値 0〜1（デフォルト: {DEFAULT_MARK_THRESH}）")
    p.add_argument("--dpi",    type=int,   default=DEFAULT_DPI,
                   help=f"処理解像度 dpi（デフォルト: {DEFAULT_DPI}、変更非推奨）")
    p.add_argument("--pages",  nargs="+",  type=int, default=None,
                   help="処理するページ番号（例: --pages 1 2 3）1始まり")
    p.add_argument("--no-crop", action="store_true",
                   help="右半分クロップを強制スキップ（縦長 PDF テスト用）")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # 設定読み込み
    try:
        config = load_config(args.config)
    except Exception as e:
        log.error(f"設定ファイル読み込みエラー: {e}")
        sys.exit(1)

    log.info(
        f"クラス: {config['class_name']} / {config.get('test_no', '')} / "
        f"大問数: {len(config['questions'])} / 満点: {config['total_max']} 点"
    )

    debug_dir = "debug" if args.debug else None

    # 各ページ処理（1ページずつ読み込み・処理して省メモリ）
    results = []
    try:
        for page_num, img in pdf_to_images(args.pdf, dpi=args.dpi, page_list=args.pages):
            try:
                result = process_page(
                    img, config, page_num,
                    thresh=args.thresh,
                    no_crop=args.no_crop,
                    debug_dir=debug_dir,
                )
            except Exception as e:
                log.error(f"ページ {page_num} 処理エラー: {e}", exc_info=True)
                result = fail_result(page_num, len(config["questions"]))
            results.append(result)
    except Exception as e:
        log.error(f"PDF 読み込みエラー: {e}")
        sys.exit(1)

    if not results:
        log.error("処理結果がありません")
        sys.exit(1)

    # Excel 出力
    try:
        write_excel(results, config, args.out)
    except Exception as e:
        log.error(f"Excel 出力エラー: {e}", exc_info=True)
        sys.exit(1)

    # サマリー
    ok  = sum(1 for r in results if r["page_flag"] == "正常")
    ng  = len(results) - ok
    log.info(f"完了: {len(results)} ページ処理（正常: {ok} / 要確認: {ng}）")


if __name__ == "__main__":
    main()
