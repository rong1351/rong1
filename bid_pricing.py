import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

# ================= 全局固定参数 =================
TAX_RATE = 0.06
SURCHARGE_RATE = 0.12
STAMP_DUTY_RATE = 0.0003

AUDIT_TYPE_FACTOR = {
    "年报审计": 1.0,
    "专项审计": 1.2,
    "IPO审计": 2.5,
    "内控审计": 1.3,
    "离任审计": 1.4,
}

ASSET_WORKLOAD = [
    (0, 5000),
    (5000, 20000),
    (20000, 50000),
    (50000, 100000),
    (100000, 300000),
    (300000, float('inf'))
]
BASE_HOURS = [80, 150, 250, 400, 600, 800]

ALL_ROLES = ["区经理", "审计副理", "审计主管", "一级审计师", "二级审计师", "三级审计师", "实习生"]

DEFAULT_RATES = {
    "区经理": 3000,
    "审计副理": 2000,
    "审计主管": 1500,
    "一级审计师": 1000,
    "二级审计师": 800,
    "三级审计师": 600,
    "实习生": 300
}
DEFAULT_COMMISSION = {
    "区经理": 2.0,
    "审计副理": 1.5,
    "审计主管": 1.0,
    "一级审计师": 0.8,
    "二级审计师": 0.6,
    "三级审计师": 0.4,
    "实习生": 0.2
}
DEFAULT_HOURS_RATIO = {
    "区经理": 0.05,
    "审计副理": 0.10,
    "审计主管": 0.15,
    "一级审计师": 0.25,
    "二级审计师": 0.20,
    "三级审计师": 0.15,
    "实习生": 0.10
}

# ================= 初始化默认值（仅首次运行） =================
for role in ALL_ROLES:
    if f"rate_{role}" not in st.session_state:
        st.session_state[f"rate_{role}"] = DEFAULT_RATES[role]
    if f"comm_{role}" not in st.session_state:
        st.session_state[f"comm_{role}"] = DEFAULT_COMMISSION[role]
if "selected_roles" not in st.session_state:
    st.session_state.selected_roles = ALL_ROLES.copy()

# ================= 核心函数 =================
def normalize_ratios(selected, ratios_dict):
    total = sum(ratios_dict[r] for r in selected)
    if total == 0:
        return {r: 0 for r in selected}
    return {r: ratios_dict[r] / total for r in selected}

def estimate_workload(asset, audit_type, subsidiaries, net_profit, selected_roles):
    idx = 0
    for i, (low, high) in enumerate(ASSET_WORKLOAD):
        if low <= asset < high:
            idx = i
            break
    base = BASE_HOURS[idx]
    factor = AUDIT_TYPE_FACTOR.get(audit_type, 1.0)
    sub_hours = subsidiaries * 8
    profit_hours = (net_profit / 1000) * 5 if net_profit > 0 else 0
    total_hours = base * factor + sub_hours + profit_hours
    ratios = {r: DEFAULT_HOURS_RATIO[r] for r in selected_roles}
    norm = normalize_ratios(selected_roles, ratios)
    return {r: total_hours * norm[r] for r in selected_roles}

def manual_total_workload(total_hours, ratios):
    total_pct = sum(ratios.values())
    if total_pct == 0:
        return {r: 0 for r in ratios}
    return {r: total_hours * (ratios[r] / total_pct) for r in ratios}

def compute_cost(workload, rates, travel, other):
    labor = sum(rates[role] * workload[role] for role in workload)
    direct = labor + travel + other
    vat = direct * TAX_RATE
    surcharge = vat * SURCHARGE_RATE
    stamp = direct * STAMP_DUTY_RATE
    total = direct + vat + surcharge + stamp
    return {
        "人工成本": labor,
        "差旅费": travel,
        "其他直接费用": other,
        "直接成本小计": direct,
        "增值税": vat,
        "附加税": surcharge,
        "印花税": stamp,
        "总成本": total
    }

def risk_adjust(price, first, industry, credit):
    factor = 1.0
    if first:
        factor += 0.2
    factor += industry * 0.1
    factor += credit * 0.05
    return price * factor

def suggest_price(cost, strategy, method):
    margin = {"稳健": 0.20, "激进": 0.10, "保守": 0.30}.get(strategy, 0.20)
    target = cost * (1 + margin)
    if method == "低价优先":
        return max(cost * 1.05, target * 0.9)
    elif method == "平均价":
        return cost * 1.25 * 0.98
    return target

# ================= 界面 =================
st.set_page_config(page_title="审计报价系统", layout="wide")
st.title("📊 审计服务招投标自动报价系统")

# ---------- 侧边栏 ----------
with st.sidebar:
    st.header("👥 参与报价的职级")
    selected_roles = st.multiselect(
        "请选择本次项目涉及的职级",
        options=ALL_ROLES,
        default=st.session_state.selected_roles,
        key="role_selector"
    )
    st.session_state.selected_roles = selected_roles

    if not selected_roles:
        st.warning("请至少选择一个职级")
        st.stop()

    st.header("⚙️ 费率与提成配置")
    st.caption("直接手写输入后按回车，费率最小可设为0")

    rates = {}
    commission_pcts = {}

    # 表头
    h1, h2, h3 = st.columns([2, 2, 2])
    h1.write("**职级**")
    h2.write("**费率 (元/小时)**")
    h3.write("**提成比例 (%)**")

    for role in selected_roles:
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            st.write(role)
        with col2:
            # number_input 自动绑定 session_state，直接手写即可
            rates[role] = st.number_input(
                f"费率_{role}",
                min_value=0, step=50,
                value=st.session_state[f"rate_{role}"],
                key=f"rate_{role}",
                label_visibility="collapsed"
            )
        with col3:
            commission_pcts[role] = st.number_input(
                f"提成_{role}",
                min_value=0.0, max_value=20.0, step=0.1,
                value=st.session_state[f"comm_{role}"],
                key=f"comm_{role}",
                label_visibility="collapsed"
            )

    st.divider()
    st.header("📈 报价策略")
    strategy = st.selectbox("报价策略", ["稳健", "激进", "保守"])
    scoring_method = st.selectbox("评分方法", ["低价优先", "平均价", "预算上限"])

# ---------- 主区域：项目参数 ----------
col1, col2, col3, col4 = st.columns(4)
with col1:
    project_name = st.text_input("项目名称", "XX公司2026年度年报审计")
    audit_type = st.selectbox("审计类型", list(AUDIT_TYPE_FACTOR.keys()))
    asset = st.number_input("资产总额（万元）", min_value=100, value=50000, step=1000)
with col2:
    subsidiaries = st.number_input("子公司数量", 0, 100, 3)
    first_engagement = st.checkbox("首次承接业务")
    travel_expense = st.number_input("差旅费（元）", value=15000, step=1000)
with col3:
    other_expense = st.number_input("其他直接费用（元）", value=5000, step=500)
    industry_risk = st.slider("行业风险", 0, 5, 2)
    credit_risk = st.slider("客户回款风险", 0, 5, 1)
with col4:
    net_profit = st.number_input("净利润总额（万元）", min_value=0, value=5000, step=100)
    hour_mode = st.radio(
        "工时计算方式",
        ["自动估算工时", "手动总工时+比例", "手动各职级工时"],
        horizontal=True
    )

# 工时额外输入
manual_workload_result = None
if hour_mode == "手动总工时+比例":
    total_hours = st.number_input("总工时（小时）", value=500, min_value=1, step=10)
    st.write("**各职级工时占比（%）**")
    ratio_cols = st.columns(len(selected_roles))
    ratios = {}
    for i, role in enumerate(selected_roles):
        default_ratio = int(DEFAULT_HOURS_RATIO[role] * 100)
        with ratio_cols[i]:
            ratios[role] = st.slider(f"{role}", 0, 100, default_ratio, step=1, key=f"ratio_{role}")
elif hour_mode == "手动各职级工时":
    st.write("**直接输入各职级工时（小时）**")
    hour_cols = st.columns(len(selected_roles))
    manual_hours = {}
    for i, role in enumerate(selected_roles):
        default_hour = int(500 * DEFAULT_HOURS_RATIO[role])
        with hour_cols[i]:
            manual_hours[role] = st.number_input(f"{role}", value=default_hour, min_value=0, step=1, key=f"hour_{role}")
    manual_workload_result = manual_hours

# ---------- 计算 ----------
if st.button("📊 开始测算报价", type="primary"):
    # 获取当前选中的职级
    roles_list = st.session_state.selected_roles

    # 工时分配
    if hour_mode == "自动估算工时":
        workload = estimate_workload(asset * 10000, audit_type, subsidiaries, net_profit * 10000, roles_list)
    elif hour_mode == "手动总工时+比例":
        workload = manual_total_workload(total_hours, ratios)
    else:
        workload = manual_workload_result

    # 成本计算（侧边栏的 rates 字典已包含最新的输入值）
    cost_details = compute_cost(workload, rates, travel_expense, other_expense)
    base_cost = cost_details["总成本"]
    risk_base = risk_adjust(base_cost, first_engagement, industry_risk, credit_risk)
    final_price = suggest_price(risk_base, strategy, scoring_method)

    # ---- 结果显示 ----
    tab1, tab2, tab3, tab4 = st.tabs(["📋 工时与成本", "💰 报价建议", "💸 提成预算", "📄 导出报价单"])

    with tab1:
        st.subheader("当前使用的费率与提成")
        rate_df = pd.DataFrame({
            "职级": roles_list,
            "费率 (元/小时)": [rates[r] for r in roles_list],
            "提成比例 (%)": [commission_pcts[r] for r in roles_list]
        })
        st.dataframe(rate_df, use_container_width=True)

        st.subheader("工时分配")
        work_df = pd.DataFrame({
            "职级": roles_list,
            "费率": [rates[r] for r in roles_list],
            "工时": [round(workload[r], 1) for r in roles_list],
            "小计": [round(rates[r] * workload[r], 0) for r in roles_list]
        })
        st.dataframe(work_df, use_container_width=True)

        st.subheader("成本明细")
        cost_df = pd.DataFrame(cost_details.items(), columns=["项目", "金额 (元)"])
        cost_df["金额 (元)"] = cost_df["金额 (元)"].round(2)
        st.dataframe(cost_df, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("直接成本", f"{cost_details['直接成本小计']:,.0f}")
        c2.metric("含税总成本", f"{base_cost:,.0f}")
        c3.metric("风险调整底价", f"{risk_base:,.0f}")

    with tab2:
        st.subheader("报价建议")
        bc1, bc2 = st.columns(2)
        bc1.metric("风险调整底价", f"{risk_base:,.0f}")
        bc2.metric("建议投标报价", f"{final_price:,.0f}",
                   delta=f"{final_price - risk_base:,.0f} 利润")
        margin = (final_price - risk_base) / final_price * 100 if final_price else 0
        st.write(f"💡 策略：**{strategy}**，预计利润率：**{margin:.1f}%**")

    with tab3:
        st.subheader("提成预算（基于最终报价）")
        total_comm = 0
        comm_items = []
        for role in roles_list:
            pct = commission_pcts[role] / 100.0
            amount = final_price * pct
            comm_items.append({"职级": role, "提成比例": f"{commission_pcts[role]}%", "提成金额": round(amount, 2)})
            total_comm += amount
        comm_df = pd.DataFrame(comm_items)
        st.dataframe(comm_df, use_container_width=True)
        st.metric("提成合计", f"{total_comm:,.0f}")
        st.caption("提成预算仅供参考，未影响成本与报价。")

    with tab4:
        st.subheader("导出 Excel")
        export_dict = {
            "项目名称": project_name,
            "审计类型": audit_type,
            "资产总额(万元)": asset,
            "净利润(万元)": net_profit,
            "子公司数量": subsidiaries,
            "首次承接": "是" if first_engagement else "否",
            "参与职级": ", ".join(roles_list),
            "风险调整底价": f"{risk_base:,.0f}",
            "建议报价": f"{final_price:,.0f}",
            "提成合计": f"{total_comm:,.0f}",
            "策略": strategy,
            "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        exp1 = pd.DataFrame([export_dict])
        exp2 = pd.DataFrame(cost_details, index=["金额"]).T.reset_index()
        exp2.columns = ["费用项目", "金额(元)"]
        exp3 = comm_df.copy()
        combined = pd.concat([
            exp1.T.reset_index().rename(columns={"index":"参数",0:"值"}),
            pd.DataFrame({"参数":[""],"值":[""]}),
            exp2.rename(columns={"费用项目":"参数","金额(元)":"值"}),
            pd.DataFrame({"参数":[""],"值":[""]}),
            exp3.rename(columns={"职级":"参数","提成比例":"值","提成金额":"值"})
        ])
        st.dataframe(combined)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            combined.to_excel(writer, index=False, sheet_name="报价明细")
        st.download_button(
            label="📥 下载报价单",
            data=output.getvalue(),
            file_name=f"{project_name}_报价单.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )