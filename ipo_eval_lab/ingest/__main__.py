"""ingest CLI（ADR-0013；工单 05）。

用法：python -m ipo_eval_lab.ingest 客户.xlsx --company-id acme_01 [--save] [--overwrite]
退出码契约：0 = 成功；1 = 违例（一次报全、不落盘）；2 = --save 防覆盖拒绝。
--save 把导入会话目录三件套复制到 enterprises/<company_id>/（gitignore），
与 fixtures/companies 物理分离；重复保存须显式 --overwrite——不可再生数据
永不静默覆盖（ADR-0013）。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Sequence

from .importer import DEFAULT_OUT_ROOT, import_profile
from .template import FIN_ROWS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENTERPRISES_ROOT = REPO_ROOT / "enterprises"

# derived 清单的人读名：模板行用原中文名，恒推导的结构字段单独说明
_DERIVED_ZH: dict[str, str] = {r.key: r.label for r in FIN_ROWS}
_DERIVED_ZH.update(
    {
        "equity_roll.net_profit_attrib_parent": "权益滚动·归母净利润（恒由利润表带出）",
        "equity_roll.closing_attrib_parent": "权益滚动·期末归母权益（恒由资产负债表带出）",
    }
)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m ipo_eval_lab.ingest",
        description="企业数据导入：标准模板 Excel → 三件套主体目录（profile.json + source.xlsx + ingest.json）",
    )
    p.add_argument("xlsx", help="客户填写的模板 Excel 路径")
    p.add_argument("--company-id", required=True, help="运营方分配的主体 ID（客户缩写+序号，如 acme_01）")
    p.add_argument("--out-root", default=None, help=f"导入会话目录根（缺省 {DEFAULT_OUT_ROOT}，可整目录清理）")
    p.add_argument("--save", action="store_true", help="同时保存到 enterprises/<company_id>/（永久，供反复测评）")
    p.add_argument(
        "--overwrite", action="store_true",
        help="--save 目标已存在时显式覆盖（默认拒绝——不可再生数据永不静默覆盖）",
    )
    p.add_argument("--enterprises-root", default=None, help=argparse.SUPPRESS)  # 测试/私有部署注入
    args = p.parse_args(argv)

    result = import_profile(args.xlsx, args.company_id, out_root=args.out_root)
    if result.status == "violations":
        print(f"导入未完成：{len(result.violations)} 处违例（已一次报全，未落盘）：")
        for v in result.violations:
            print(f"  - {v}")
        return 1

    assert result.company_dir is not None
    print(f"已导入：{result.company_dir}")
    if result.derived_fields:
        print("推导字段（客户留空，导入器按勾稽恒等式推导——代跑时请留意）：")
        for k in result.derived_fields:
            print(f"  - {_DERIVED_ZH.get(k, k)}")
    else:
        print("无推导字段：全部数值来自客户原填。")

    if args.save:
        root = Path(args.enterprises_root) if args.enterprises_root else DEFAULT_ENTERPRISES_ROOT
        dest = root / args.company_id
        if dest.exists() and not args.overwrite:
            print(
                f"保存失败：{dest} 已存在。不可再生数据永不静默覆盖——"
                f"确认替换请加 --overwrite，或更换 --company-id。",
                file=sys.stderr,
            )
            return 2
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(result.company_dir, dest)
        print(f"已保存主体：{dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
