"""规则库 YAML schema 的 pydantic 模型与加载期断言。

对应设计 0002（R1~R6 已按推荐拍板，2026-11-10）。lint 分工：
- L1 量纲一致 / L3 套结构 / L4 引用完整 / L5 窗口 token / L6 evidence 必填 → 本文件模型断言
- L2 组合覆盖（全局）→ loader（样板期警告，strict 报错）
- L7 快照对拍 → scripts/trace_check.py（步骤 3，暂缺）
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ── 枚举（op/format 实测快照仅出现 eq/gt/ge，枚举全量预留）──


class Op(str, Enum):
    eq = "eq"
    ne = "ne"
    gt = "gt"
    ge = "ge"
    lt = "lt"
    le = "le"


class ThresholdFormat(str, Enum):
    number = "number"
    percent = "percent"
    integer = "integer"
    boolean = "boolean"


class Nature(str, Enum):
    quantitative = "quantitative"  # 可计算
    documentary = "documentary"    # 可核验事实（填报值）
    judgment = "judgment"          # 需专业意见（永不 met → needs_review）


class BasisKind(str, Enum):
    calc = "calc"
    worksheet = "worksheet"
    declared = "declared"


class Quantifier(str, Enum):
    latest = "latest"
    all_periods = "all_periods"
    sum = "sum"
    avg = "avg"
    cagr = "cagr"
    ratio = "ratio"


class Lever(str, Enum):
    grow = "grow"
    derived = "derived"
    wait = "wait"
    adjust = "adjust"
    act = "act"


class Scope(str, Enum):
    set = "set"
    issuance = "issuance"
    positioning = "positioning"


# metric.unit → 允许的 threshold.format（lint L1 基准；ratio 项固定 percent）
UNIT_TO_FORMAT: dict[str, ThresholdFormat] = {
    "yuan": ThresholdFormat.number,
    "percent": ThresholdFormat.percent,
    "count": ThresholdFormat.integer,
    "year": ThresholdFormat.integer,
    "boolean": ThresholdFormat.boolean,
}


# ── 窗口（L5：只允许 token，语义由公式引擎单点实现，设计 0002 §3）──


class Window(BaseModel):
    kind: Literal["nth_year", "last_n_years", "latest"]
    n: Optional[int] = None

    @model_validator(mode="after")
    def _token_shape(self) -> "Window":
        if self.kind == "latest" and self.n is not None:
            raise ValueError("L5 window=latest 不带 n")
        if self.kind == "nth_year" and not (self.n is not None and 1 <= self.n <= 3):
            raise ValueError("L5 window=nth_year 需要 n ∈ 1..3")
        if self.kind == "last_n_years" and not (self.n is not None and 2 <= self.n <= 3):
            raise ValueError("L5 window=last_n_years 需要 n ∈ 2..3（v1 报告期为三个完整年度）")
        return self


# ── 阈值 / 叶 / 条文 / 支路 / 官方套 ──


class Threshold(BaseModel):
    value: Union[bool, int, float]
    format: ThresholdFormat

    @model_validator(mode="after")
    def _value_type(self) -> "Threshold":
        v, f = self.value, self.format
        if f is ThresholdFormat.boolean and not isinstance(v, bool):
            raise ValueError("boolean 阈值必须为 true/false")
        if f is ThresholdFormat.integer and (isinstance(v, bool) or not isinstance(v, int)):
            raise ValueError("integer 阈值必须为整数")
        if f in (ThresholdFormat.number, ThresholdFormat.percent) and isinstance(v, bool):
            raise ValueError("number/percent 阈值不得为布尔")
        return self


class Alias(BaseModel):
    midas: list[str] = Field(default_factory=list)


class Leaf(BaseModel):
    leaf_id: str
    item_ref: str
    op: Op
    threshold: Threshold
    note: Optional[str] = None


class Clause(BaseModel):
    clause_id: str
    display: Optional[str] = None
    law_ref: str  # L6 必填，格式 law_id#article（article 可带 (一) 后缀）
    logic: Literal["all", "any"] = "all"  # 条文内择一 → any（R2-a）
    leaves: list[Leaf] = Field(min_length=1)
    note: Optional[str] = None


class Branch(BaseModel):
    set_id: str  # branch = set_id（层②/差距画像的引用单元）
    display: Optional[str] = None
    aliases: Alias = Field(default_factory=Alias)
    clauses: list[Clause] = Field(min_length=1)


class Group(BaseModel):
    scope: Scope = Scope.set
    group_id: str
    display: str
    boards: list[str] = Field(min_length=1)
    company_type: str  # v1 单类型；多类型适用性走多 group 或 positioning 扩展
    group_no: Optional[int] = None  # 官方套号，仅编号不排序（A3）
    section: Optional[str] = None  # issuance 用：L1 四节标签
    effective_from: date  # L6 必填（D2 简化：effective_to/过渡期 v2）
    law_refs: list[str] = Field(default_factory=list)
    shared_clauses: list[Clause] = Field(default_factory=list)  # 不变量 #6 的结构化载体
    branches: list[Branch] = Field(min_length=1)
    aliases: Alias = Field(default_factory=Alias)
    note: Optional[str] = None

    @model_validator(mode="after")
    def _l3(self) -> "Group":
        if self.scope is Scope.set and len(self.branches) > 1 and not self.shared_clauses:
            raise ValueError(
                f"L3 段③多 branch 的 group 必须有 shared_clauses（不变量 #6）：{self.group_id}"
            )
        if self.scope is Scope.issuance and self.section is None:
            raise ValueError(f"L3 issuance 作用域的 group 必须带 section（L1 四节）：{self.group_id}")
        return self


# ── 指标 / 条件型 / 法条 / 全局 ──


class Measures(BaseModel):
    deduction: list[str] = Field(default_factory=list)
    audit: list[str] = Field(default_factory=list)


class Metric(BaseModel):
    metric_id: str
    display: str
    unit: Literal["yuan", "percent", "count", "year", "boolean"]
    kind: Literal["flow", "stock", "derived", "documentary"]
    basis: Optional[str] = None  # 口径说明：attrib_parent / weighted_average / self_estimate
    measures: Optional[Measures] = None
    decision_measure: Optional[str] = None  # 如 lower_of_both（ADR-0003）
    sources: Optional[dict] = None
    note: Optional[str] = None


class Item(BaseModel):
    """条件型：可复用的条件类型（量词+窗口+指标），不带阈值；阈值在 leaf（R4）。"""

    item_id: str
    display: str
    nature: Nature
    basis: BasisKind
    metric_ref: Optional[str] = None
    quantifier: Optional[Quantifier] = None
    window: Optional[Window] = None
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    lever: Lever
    driver_ids: list[str] = Field(default_factory=list)
    aliases: Alias = Field(default_factory=Alias)
    pending_evidence: list[str] = Field(default_factory=list)
    note: Optional[str] = None

    @model_validator(mode="after")
    def _shape(self) -> "Item":
        if self.nature is Nature.judgment:
            if self.basis is not BasisKind.declared:
                raise ValueError(f"judgment × declared 才合法（ADR-0003 判定矩阵）：{self.item_id}")
            if self.metric_ref or self.quantifier or self.window or self.numerator or self.denominator:
                raise ValueError(f"judgment 项不挂取数结构：{self.item_id}")
            if not self.pending_evidence:
                raise ValueError(f"judgment 项必须给出 pending_evidence：{self.item_id}")
        elif self.nature is Nature.documentary:
            if self.basis is not BasisKind.worksheet:
                raise ValueError(f"documentary × worksheet 才合法：{self.item_id}")
            if self.quantifier or self.window or self.numerator or self.denominator:
                raise ValueError(f"documentary 项不带量词/窗口/分子分母：{self.item_id}")
        else:  # quantitative
            if self.basis is not BasisKind.calc:
                raise ValueError(f"quantitative × calc 才合法：{self.item_id}")
            if not (self.quantifier and self.window):
                raise ValueError(f"quantitative 项需要 quantifier+window：{self.item_id}")
            if self.quantifier is Quantifier.ratio:
                if not (self.numerator and self.denominator):
                    raise ValueError(f"ratio 项需要 numerator+denominator：{self.item_id}")
                if self.metric_ref:
                    raise ValueError(f"ratio 项不挂 metric_ref（分子分母即口径）：{self.item_id}")
            else:
                if not self.metric_ref:
                    raise ValueError(f"非 ratio 的 quantitative 项需要 metric_ref：{self.item_id}")
                if self.numerator or self.denominator:
                    raise ValueError(f"非 ratio 项不带分子分母：{self.item_id}")
        return self


class LawArticle(BaseModel):
    article: str
    text: str
    note: Optional[str] = None


class Law(BaseModel):
    law_id: str
    title: str
    source_type: Literal["law", "exchange_rule", "guideline_qa"]  # C4 简化三值
    effective_from: date
    articles: list[LawArticle] = Field(min_length=1)
    calibration_pending: bool = False
    note: Optional[str] = None


class Conventions(BaseModel):
    percent: Literal["decimal"]
    money: Literal["yuan"]
    op: list[str]
    format: list[str]


class Meta(BaseModel):
    rulebook_version: str = Field(min_length=1)
    conventions: Conventions
    boards: list[str] = Field(min_length=1)
    company_types: list[str] = Field(min_length=1)
    declared_no_sets: list[list[str]] = Field(default_factory=list)  # L2 豁免：法定无套组合


class Rulebook(BaseModel):
    """跨实体校验（L1/L4/L6 + 标识唯一性 + midas 别名唯一挂载）。"""

    meta: Meta
    metrics: list[Metric] = Field(min_length=1)
    items: list[Item] = Field(min_length=1)
    laws: list[Law] = Field(min_length=1)
    groups: list[Group] = Field(min_length=1)

    @model_validator(mode="after")
    def _cross(self) -> "Rulebook":
        errors: list[str] = []

        def check_dup(names: list[str], label: str) -> None:
            seen: set[str] = set()
            dupes: set[str] = set()
            for n in names:
                (dupes if n in seen else seen).add(n)
            if dupes:
                errors.append(f"L4 {label} 重复：{sorted(dupes)}")

        check_dup([m.metric_id for m in self.metrics], "metric_id")
        check_dup([i.item_id for i in self.items], "item_id")
        check_dup([l.law_id for l in self.laws], "law_id")
        check_dup([g.group_id for g in self.groups], "group_id")
        check_dup([b.set_id for g in self.groups for b in g.branches], "set_id")

        metrics = {m.metric_id: m for m in self.metrics}
        items = {i.item_id: i for i in self.items}
        laws = {l.law_id: l for l in self.laws}

        for it in self.items:
            for ref in [r for r in (it.metric_ref, it.numerator, it.denominator) if r]:
                if ref not in metrics:
                    errors.append(f"L4 item {it.item_id} 引用未定义 metric：{ref}")

        boards = set(self.meta.boards)
        types = set(self.meta.company_types)
        midas_seen: set[str] = set()

        def take_midas(alias: Alias, where: str) -> None:
            for a in alias.midas:
                if a in midas_seen:
                    errors.append(f"L4 midas 别名 {a} 重复挂载（{where}）")
                midas_seen.add(a)

        def check_clause(c: Clause, g: Group) -> None:
            law_id, _, art = c.law_ref.partition("#")
            if not law_id or not art:
                errors.append(f"L6 clause {c.clause_id} law_ref 应为 law_id#article：{c.law_ref}")
            else:
                law = laws.get(law_id)
                if law is None:
                    errors.append(f"L4 clause {c.clause_id} 指向未定义法条：{law_id}")
                elif not any(a.article == art.split("(")[0] for a in law.articles):
                    errors.append(f"L6 clause {c.clause_id}：法条 {law_id} 无条款 {art}")
            for lf in c.leaves:
                it = items.get(lf.item_ref)
                if it is None:
                    errors.append(f"L4 leaf {lf.leaf_id} 引用未定义 item：{lf.item_ref}")
                    continue
                # L1 量纲一致：ratio→percent；judgment→boolean；其余按 metric.unit
                if it.quantifier is Quantifier.ratio:
                    expected: Optional[ThresholdFormat] = ThresholdFormat.percent
                elif it.nature is Nature.judgment:
                    expected = ThresholdFormat.boolean
                elif it.metric_ref:
                    expected = UNIT_TO_FORMAT[metrics[it.metric_ref].unit]
                else:
                    expected = None
                if expected is not None and lf.threshold.format is not expected:
                    errors.append(
                        f"L1 leaf {lf.leaf_id}（item {it.item_id}）阈值 format="
                        f"{lf.threshold.format.value}，应为 {expected.value}"
                    )

        for g in self.groups:
            for b in g.boards:
                if b not in boards:
                    errors.append(f"L4 group {g.group_id} 板块 {b} 不在 _meta.boards")
            if g.company_type not in types:
                errors.append(f"L4 group {g.group_id} 类型 {g.company_type} 不在 _meta.company_types")
            take_midas(g.aliases, g.group_id)

            clause_count: dict[str, int] = {}
            all_clauses = list(g.shared_clauses) + [c for br in g.branches for c in br.clauses]
            for c in all_clauses:
                clause_count[c.clause_id] = clause_count.get(c.clause_id, 0) + 1
                check_clause(c, g)
            for cid, n in clause_count.items():
                if n > 1:
                    errors.append(f"L4 clause_id {cid} 在 group {g.group_id} 内重复")
            for br in g.branches:
                take_midas(br.aliases, br.set_id)

        if errors:
            raise ValueError("规则库 lint 失败：\n- " + "\n- ".join(errors))
        return self
