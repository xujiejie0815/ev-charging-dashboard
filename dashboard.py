import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

st.set_page_config(page_title="EV充電 利用状況ダッシュボード", layout="wide")

# ===== パスワード認証 =====
def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.title("🔐 EV充電 利用状況ダッシュボード")
    pwd = st.text_input("パスワード", type="password", placeholder="パスワードを入力してください")
    if st.button("ログイン", type="primary"):
        correct = st.secrets.get("PASSWORD", "")
        if pwd and pwd == correct:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()

check_password()

# ===== データパス（ローカル or デプロイ環境） =====
_local = "/Users/j.joplugo.co.jp/Documents/all_facilities_usage_v5.csv"
_deploy = os.path.join(os.path.dirname(__file__), "data", "all_facilities_usage_v5.csv")
DATA_PATH = _local if os.path.exists(_local) else _deploy

@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    df["充電器グループID"] = df["充電器グループID"].astype(str)
    df["year"] = df["利用月"].str.extract(r"(\d{4})-").astype(int)
    df["month"] = df["利用月"].str.extract(r"-(\d+)月").astype(int)
    df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
    df["稼働時間_h"] = pd.to_numeric(df["稼働時間(分)"], errors="coerce").fillna(0) / 60
    df["利用回数"] = pd.to_numeric(df["利用回数"], errors="coerce").fillna(0)
    df["利用人数"] = pd.to_numeric(df["利用人数"], errors="coerce").fillna(0)
    df["台数"] = pd.to_numeric(df["台数"], errors="coerce").fillna(1)
    df["日数"] = pd.to_numeric(df["日数"], errors="coerce").fillna(30)
    # 稼働率を数値に変換
    df["稼働率_pct"] = pd.to_numeric(
        df["稼働率"].astype(str).str.replace("%", "").str.strip(), errors="coerce"
    ).fillna(0)
    # 再計算（稼働開始日以降のみ正の稼働率を許容）
    df["稼働率_calc"] = (
        df["稼働時間(分)"] / (df["日数"] * 24 * 60 * df["台数"]) * 100
    ).clip(lower=0).round(2)
    df["ブランド"] = df["ブランド"].fillna("").astype(str)
    df["運営会社"] = df["運営会社"].fillna("").astype(str)
    # 稼働終了日を datetime に変換
    df["稼働終了日_dt"] = pd.to_datetime(
        df["稼働終了日(手動)"].astype(str).str.strip().replace("", pd.NA),
        errors="coerce"
    )
    # 稼働率計算用の分母
    df["稼働可能分"] = df["日数"] * 24 * 60 * df["台数"]
    return df

df_all = load_data()

# ===== サイドバー =====
st.sidebar.header("フィルター")

# 稼働終了日が設定されている施設は終了日前のデータのみ使用
# 終了日なし → そのまま含める
# 終了日あり → 終了日の月まで含める（終了日以降は除外）
df_base = df_all[
    df_all["稼働終了日_dt"].isna() | (df_all["date"] <= df_all["稼働終了日_dt"])
].copy()

# 期間フィルター（2025-12まで）
df_base = df_base[df_base["date"] <= pd.Timestamp("2025-12-01")]

# カスケードフィルター（複数選択可・未選択=すべて）
sel_cats = st.sidebar.multiselect(
    "カテゴリー",
    sorted(df_base["カテゴリー"].dropna().unique().tolist()),
    placeholder="すべて",
)
df_f1 = df_base if not sel_cats else df_base[df_base["カテゴリー"].isin(sel_cats)]

sel_brands = st.sidebar.multiselect(
    "ブランド",
    sorted([b for b in df_f1["ブランド"].dropna().unique() if b]),
    placeholder="すべて",
)
df_f2 = df_f1 if not sel_brands else df_f1[df_f1["ブランド"].isin(sel_brands)]

sel_models = st.sidebar.multiselect(
    "モデル",
    sorted(df_f2["モデル"].dropna().unique().tolist()),
    placeholder="すべて",
)
df_f3 = df_f2 if not sel_models else df_f2[df_f2["モデル"].isin(sel_models)]

# 期間スライダー
date_min = df_base["date"].min()
date_max = df_base["date"].max()
date_range = st.sidebar.slider(
    "期間",
    min_value=date_min.to_pydatetime(),
    max_value=date_max.to_pydatetime(),
    value=(date_min.to_pydatetime(), date_max.to_pydatetime()),
    format="YYYY-MM",
)
df_filtered = df_f3[
    (df_f3["date"] >= date_range[0]) & (df_f3["date"] <= date_range[1])
]

# ===== ヘッダー =====
st.title("⚡ EV充電 利用状況ダッシュボード")
n_fac = df_filtered["充電器グループID"].nunique()
st.caption(
    f"対象施設: {n_fac} 施設 ／ 期間: {date_range[0].strftime('%Y-%m')} 〜 {date_range[1].strftime('%Y-%m')}"
)

# ===== KPIカード（フィルター後全体） =====
active = df_filtered[df_filtered["利用回数"] > 0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("総利用回数", f"{int(active['利用回数'].sum()):,} 回")
c2.metric("総利用人数", f"{int(active['利用人数'].sum()):,} 人")
c3.metric("総稼働時間", f"{active['稼働時間_h'].sum():,.0f} 時間")
c4.metric("平均稼働率", f"{active['稼働率_calc'].mean():.1f} %")

st.divider()

# ===== タブ =====
tab1, tab2, tab3 = st.tabs(["📍 ① 施設別ビュー", "📊 ② カテゴリ・ブランド・モデル別", "📋 ③ RAWデータ"])

# ──────────────────────────────────────────
# TAB 1: 施設別ビュー
# ──────────────────────────────────────────
with tab1:
    # GID単位で施設リストを作成（同名・複数モデルは [普通]/[急速] を付与）
    fac_meta = (
        df_filtered[["充電器グループID", "施設名", "モデル"]]
        .drop_duplicates("充電器グループID")
        .copy()
    )
    name_counts = fac_meta["施設名"].value_counts()
    fac_meta["label"] = fac_meta.apply(
        lambda r: f"{r['施設名']} [{r['モデル']}]"
        if name_counts[r["施設名"]] > 1 else r["施設名"],
        axis=1,
    )
    fac_meta = fac_meta.sort_values("label")
    label_to_gid = dict(zip(fac_meta["label"], fac_meta["充電器グループID"]))

    if fac_meta.empty:
        st.warning("条件に合う施設がありません。")
    else:
        sel_label = st.selectbox("施設名", fac_meta["label"].tolist(), key="fac_select")
        sel_gid = label_to_gid[sel_label]
        df_fac = df_filtered[df_filtered["充電器グループID"] == sel_gid].sort_values("date")

        # 施設情報
        info = df_fac.iloc[0]
        col_info1, col_info2, col_info3, col_info4, col_info5 = st.columns(5)
        col_info1.metric("グループID", info["充電器グループID"])
        col_info2.metric("モデル", info["モデル"])
        col_info3.metric("カテゴリー", info["カテゴリー"])
        col_info4.metric("ブランド", info["ブランド"] or "—")
        col_info5.metric("台数", f"{int(info['台数'])} 台")

        st.caption(f"稼働開始日: {info['稼働開始日']}　|　運営会社: {info['運営会社'] or '—'}")

        st.divider()

        # KPI
        fac_active = df_fac[df_fac["利用回数"] > 0]
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("総利用回数", f"{int(fac_active['利用回数'].sum()):,} 回")
        k2.metric("総利用人数", f"{int(fac_active['利用人数'].sum()):,} 人")
        k3.metric("総稼働時間", f"{fac_active['稼働時間_h'].sum():,.1f} 時間")
        k4.metric("平均稼働率", f"{fac_active['稼働率_calc'].mean():.2f} %")
        k5.metric("稼働月数 / 対象月数", f"{len(fac_active)} / {len(df_fac)}")

        # 指標選択
        metric_opt = st.radio(
            "表示指標",
            ["利用回数", "利用人数", "稼働時間（時間）", "稼働率（%）"],
            horizontal=True,
            key="fac_metric",
        )
        col_map = {
            "利用回数": "利用回数",
            "利用人数": "利用人数",
            "稼働時間（時間）": "稼働時間_h",
            "稼働率（%）": "稼働率_calc",
        }

        y_col = col_map[metric_opt]
        use_line = metric_opt == "稼働率（%）"

        if use_line:
            fig = go.Figure()
            fig.add_scatter(
                x=df_fac["date"],
                y=df_fac[y_col],
                mode="lines+markers+text",
                name=metric_opt,
                line=dict(color="#3B82F6", width=2),
                marker=dict(size=6),
                text=df_fac[y_col].apply(lambda v: f"{v:.1f}%"),
                textposition="top center",
                textfont=dict(size=10),
            )
        else:
            fig = go.Figure()
            fig.add_bar(
                x=df_fac["date"],
                y=df_fac[y_col],
                name=metric_opt,
                marker_color="#3B82F6",
                text=df_fac[y_col].apply(lambda v: f"{int(v):,}" if v > 0 else ""),
                textposition="outside",
                textfont=dict(size=10),
            )

        fig.update_layout(
            title=f"{sel_label} ／ 月次 {metric_opt}",
            xaxis_title="月",
            yaxis_title=metric_opt,
            height=420,
            hovermode="x unified",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        # 月次詳細テーブル
        with st.expander("月次詳細データ"):
            disp = df_fac[["利用月", "台数", "稼働時間(分)", "稼働時間_h", "利用人数", "利用回数", "稼働率_calc"]].copy()
            disp.columns = ["利用月", "台数", "稼働時間(分)", "稼働時間(時間)", "利用人数", "利用回数", "稼働率(%)"]
            st.dataframe(disp.set_index("利用月"), use_container_width=True)

# ──────────────────────────────────────────
# TAB 2: カテゴリ・ブランド・モデル別
# ──────────────────────────────────────────
with tab2:
    group_by = st.radio(
        "集計軸",
        ["カテゴリー", "ブランド", "モデル"],
        horizontal=True,
        key="group_axis",
    )

    # 月次時系列 + 合計比較
    metric2 = st.radio(
        "指標",
        ["利用回数", "利用人数", "稼働時間（時間）", "台数", "稼働率（%）"],
        horizontal=True,
        key="tab2_metric",
    )

    # 月次集計（稼働率は加重平均で計算）
    monthly_g = (
        df_filtered.groupby(["date", group_by])
        .agg(
            利用回数=("利用回数", "sum"),
            利用人数=("利用人数", "sum"),
            稼働時間_h=("稼働時間_h", "sum"),
            台数=("台数", "sum"),
            _稼働時間分=("稼働時間(分)", "sum"),
            _稼働可能分=("稼働可能分", "sum"),
        )
        .reset_index()
    )
    monthly_g["稼働率（%）"] = (monthly_g["_稼働時間分"] / monthly_g["_稼働可能分"] * 100).clip(lower=0).round(2)

    col_map2 = {
        "利用回数": "利用回数",
        "利用人数": "利用人数",
        "稼働時間（時間）": "稼働時間_h",
        "台数": "台数",
        "稼働率（%）": "稼働率（%）",
    }

    y_col2 = col_map2[metric2]
    use_line2 = metric2 == "稼働率（%）"

    # フォーマット定義
    text_fmt = {
        "利用回数":      lambda v: f"{int(v):,}",
        "利用人数":      lambda v: f"{int(v):,}",
        "稼働時間（時間）": lambda v: f"{v:.1f}",
        "台数":         lambda v: f"{int(v):,}",
        "稼働率（%）":   lambda v: f"{v:.2f}%",
    }
    tmpl_fmt = {
        "利用回数":      "%{y:,.0f}",
        "利用人数":      "%{y:,.0f}",
        "稼働時間（時間）": "%{y:.1f}",
        "台数":         "%{y:,.0f}",
        "稼働率（%）":   "%{y:.2f}%",
    }

    if use_line2:
        fig_trend = px.line(
            monthly_g,
            x="date",
            y=y_col2,
            color=group_by,
            title=f"月次 {metric2}（{group_by}別）",
            labels={"date": "月", y_col2: metric2},
            markers=True,
            text=monthly_g[y_col2].apply(text_fmt[metric2]),
        )
        fig_trend.update_traces(textposition="top center", textfont_size=10)

        # 稼働率のみ：全体加重平均ラインを追加
        if metric2 == "稼働率（%）" and monthly_g[group_by].nunique() > 1:
            overall = (
                df_filtered.groupby("date")
                .agg(_m=("稼働時間(分)", "sum"), _p=("稼働可能分", "sum"))
                .reset_index()
            )
            overall["稼働率（%）"] = (overall["_m"] / overall["_p"] * 100).clip(lower=0).round(2)
            fig_trend.add_scatter(
                x=overall["date"],
                y=overall["稼働率（%）"],
                mode="lines+markers+text",
                name="全体加重平均",
                line=dict(color="black", width=2, dash="dash"),
                marker=dict(size=5, symbol="diamond"),
                text=overall["稼働率（%）"].apply(lambda v: f"{v:.2f}%"),
                textposition="bottom center",
                textfont=dict(size=9, color="black"),
            )
    else:
        n_groups = monthly_g[group_by].nunique()
        fig_trend = px.bar(
            monthly_g,
            x="date",
            y=y_col2,
            color=group_by,
            title=f"月次 {metric2}（{group_by}別）",
            labels={"date": "月", y_col2: metric2},
            barmode="stack",
            text=y_col2 if n_groups == 1 else None,
        )
        if n_groups == 1:
            fig_trend.update_traces(
                texttemplate=tmpl_fmt[metric2],
                textposition="outside",
                textfont_size=10,
            )
    fig_trend.update_layout(height=400, hovermode="x unified")
    st.plotly_chart(fig_trend, use_container_width=True)

    st.divider()
    st.subheader(f"{group_by}別 サマリー")

    # 合計サマリー（全月対象、稼働率は加重平均）
    summary_agg = (
        df_filtered.groupby(group_by)
        .agg(
            施設数=("充電器グループID", "nunique"),
            _台数分=("台数", "sum"),   # 施設ごとの台数合計用
            総稼働時間_h=("稼働時間_h", "sum"),
            総利用回数=("利用回数", "sum"),
            総利用人数=("利用人数", "sum"),
            _稼働時間分=("稼働時間(分)", "sum"),
            _稼働可能分=("稼働可能分", "sum"),
        )
        .reset_index()
    )
    # 台数は施設ごとのmax台数の合計（重複カウントしない）
    台数_per_fac = df_filtered.groupby(["充電器グループID", group_by])["台数"].max().reset_index()
    台数_sum = 台数_per_fac.groupby(group_by)["台数"].sum().reset_index()
    台数_sum.columns = [group_by, "総台数"]
    summary_agg = summary_agg.merge(台数_sum, on=group_by, how="left")
    summary_agg["稼働率(%)"] = (summary_agg["_稼働時間分"] / summary_agg["_稼働可能分"] * 100).clip(lower=0).round(2)
    summary = summary_agg[[group_by, "施設数", "総台数", "総稼働時間_h", "総利用回数", "総利用人数", "稼働率(%)"]].copy()
    summary.columns = [group_by, "施設数", "総台数", "総稼働時間(時間)", "総利用回数", "総利用人数", "稼働率(%)"]
    summary["総稼働時間(時間)"] = summary["総稼働時間(時間)"].round(1)
    summary = summary.sort_values("総利用回数", ascending=False).reset_index(drop=True)

    # テーブル（フォーマット統一）
    st.dataframe(
        summary,
        use_container_width=True,
        column_config={
            "施設数":         st.column_config.NumberColumn(format="%d"),
            "総台数":         st.column_config.NumberColumn(format="%d"),
            "総稼働時間(時間)": st.column_config.NumberColumn(format="%.1f"),
            "総利用回数":      st.column_config.NumberColumn(format="%d"),
            "総利用人数":      st.column_config.NumberColumn(format="%d"),
            "稼働率(%)":      st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

    # 比較チャート群
    c_left, c_right = st.columns(2)
    with c_left:
        fig_bar = px.bar(
            summary,
            x=group_by,
            y="総利用回数",
            color=group_by,
            title=f"{group_by}別 総利用回数",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_bar.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)
    with c_right:
        fig_pie = px.pie(
            summary,
            values="総稼働時間(時間)",
            names=group_by,
            title=f"{group_by}別 稼働時間シェア",
            hole=0.4,
        )
        fig_pie.update_layout(height=350)
        st.plotly_chart(fig_pie, use_container_width=True)

    c_left2, c_right2 = st.columns(2)
    with c_left2:
        fig_util = px.bar(
            summary.sort_values("稼働率(%)"),
            x="稼働率(%)",
            y=group_by,
            orientation="h",
            title=f"{group_by}別 稼働率",
            color="稼働率(%)",
            color_continuous_scale="Blues",
        )
        fig_util.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig_util, use_container_width=True)
    with c_right2:
        fig_users = px.bar(
            summary,
            x=group_by,
            y="総利用人数",
            color=group_by,
            title=f"{group_by}別 総利用人数",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_users.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig_users, use_container_width=True)

# ──────────────────────────────────────────
# TAB 3: RAWデータ
# ──────────────────────────────────────────
with tab3:
    st.subheader("RAWデータ一覧")

    disp_cols = [
        "充電器グループID", "施設ID", "施設名", "ブランド", "カテゴリー", "モデル",
        "利用月", "日数", "台数", "稼働開始日", "稼働終了日(手動)",
        "稼働時間(分)", "稼働時間_h", "利用人数", "利用回数", "稼働率_calc",
        "1人あたりの利用分数", "1回あたりの利用分数", "平均利用頻度",
    ]
    rename_map = {"稼働時間_h": "稼働時間(時間)", "稼働率_calc": "稼働率(%)"}

    df_disp = df_filtered[disp_cols].rename(columns=rename_map).copy()
    df_disp["稼働率(%)"] = df_disp["稼働率(%)"].round(2)

    st.caption(f"{len(df_disp):,} 行 ／ {df_disp['充電器グループID'].nunique()} 施設")
    st.dataframe(df_disp, use_container_width=True, height=500)

    # CSVダウンロード
    csv_bytes = df_disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "CSVダウンロード",
        data=csv_bytes,
        file_name="ev_usage_filtered.csv",
        mime="text/csv",
    )
