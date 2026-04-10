
#excute 

# C:\Users\ASUS\fin_chips

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import google.generativeai as genai
from datetime import date,datetime
import time

import requests
from io import StringIO
from bs4 import BeautifulSoup
import plotly.graph_objects as go


headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/"
}


# --- 1. 配置與核心 Function 區 ---

def crawl_pure_data():
    # 1. 目標網址
    url = "https://www.cmoney.tw/forum/stock/rank/institutional-investor-buy?period=week"
    
    try:
        print("🚀 正在發送 Requests 請求...")
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ 伺服器拒絕連線，狀態碼：{response.status_code}")
            return None

        # 3. 解析內容
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尋找表格行數
        rows = soup.select('tbody > tr')
        
        if not rows:
            print("👻 警報：HTML 原始碼中找不到表格資料！")
            print("💡 結論：這代表 CMoney 的資料是『動態載入』，Requests 抓不到『殼』裡面的東西。")
            return None

        final_list = []
        for row in rows[:50]:
            try:
                cols = row.find_all('td')
                
                # 提取各欄位資料
                name = row.select_one('p.table__stockName').text.strip()
                ticker = row.select_one('p.table__stockId').text.strip()
                price = cols[2].text.strip().replace(',', '')
                s_range = cols[3].text.strip()
                
                # 處理數值欄位
                foreign = cols[4].text.strip().replace(',', '')
                sitc = cols[5].text.strip().replace(',', '')
                total = cols[7].text.strip().replace(',', '')

                # 排除 '-' 的情況，避免 float/int 轉換失敗
                f_val = int(foreign) if foreign != '-' else 0
                s_val = int(sitc) if sitc != '-' else 0
                t_val = int(total) if total != '-' else 0
                p_val = float(price) if price != '-' else 0.0

                final_list.append({
                    "代號": ticker,
                    "名稱": name,
                    "股票股價": p_val,
                    "漲跌幅": s_range,
                    "籌碼力道": f_val * 1.0 + s_val * 1.5,
                    "外資買賣超": f_val,
                    "投信買賣超": s_val,
                    "法人買賣超": t_val
                })
            except Exception:
                continue

        # 4. 排序與輸出
        df = pd.DataFrame(final_list)
        df_sort = df.sort_values(by="籌碼力道", ascending=False).reset_index(drop=True)
        
        print("✅ 籌碼數據獲取成功！")
        return df_sort

    except Exception as e:
        print(f"❌ 發生異常錯誤: {e}")
        return None

# 執行並查看結果
result_df = crawl_pure_data()
if result_df is not None:
    print(result_df)

def get_advanced_major_cost(ticker_list):
    costs, last_vols = [], []
    for ticker in ticker_list:
        t = str(ticker).split('.')[0].strip().zfill(4)
        data = pd.DataFrame()
        for suffix in [".TW", ".TWO"]:
            try:
                stock = yf.Ticker(f"{t}{suffix}")
                data = stock.history(period="1mo")
                if not data.empty and len(data) >= 5: break
            except: continue
        
        if not data.empty and len(data) >= 5:
            df_5d = data.tail(5).copy()
            df_5d['TP'] = (df_5d['High'] + df_5d['Low'] + df_5d['Close']) / 3
            df_5d['TP_Vol'] = df_5d['TP'] * df_5d['Volume']
            total_vol = df_5d['Volume'].sum()
            last_day_vol = df_5d['Volume'].iloc[-1]
            
            if total_vol > 0:
                vwap_cost = df_5d['TP_Vol'].sum() / total_vol
                vol_ratio = last_day_vol / df_5d['Volume'].mean()
                final_cost = (vwap_cost * 0.7) + (df_5d['TP'].iloc[-1] * 0.3) if vol_ratio > 2 else vwap_cost
                costs.append(round(final_cost, 2))
                last_vols.append(last_day_vol)
            else:
                costs.append(np.nan); last_vols.append(np.nan)
        else:
            costs.append(np.nan); last_vols.append(np.nan)
    return costs, last_vols

def get_bottom_status_v2(row):
    price, cost, change = row['股票股價'], row['主力5日成本'], row['漲跌幅_num']
    if price > cost and price <= (cost * 1.03) and change >= 0: return "🔥 底部起漲"
    elif price > cost and change < 0: return "⚠️ 高檔轉弱 (避開)"
    elif price < cost and change < -2: return "📉 趨勢轉空"
    elif price <= cost and price >= (cost * 0.97): return "💎 鎖碼盤整"
    else: return "🔎 觀察中"
    

def make_clickable(ticker):
    # 針對台股代號，加上 .TW (上市) 或 .TWO (上櫃) 的跳轉邏輯，這裡簡化使用 Yahoo 搜尋或直接導向
    url = f"https://www.cmoney.tw/forum/stock/{ticker}"
    return f'<a target="_blank" href="{url}" style="text-decoration: none; color: #1f77b4;">{ticker}</a>'

# --- 2. 整合分析流程 ---

def run_full_analysis(total_budget, num_stocks):
    result_df = crawl_pure_data()
    if result_df is None or result_df.empty: return None

    costs, last_vols = get_advanced_major_cost(result_df['代號'])
    result_df['主力5日成本'] = costs
    result_df['今日成交量'] = last_vols
    result_df['主力5日成本'] = result_df['主力5日成本'].fillna(result_df['股票股價'])
    
    # 核心修正：轉換漲跌幅為數字
    result_df['漲跌幅_num'] = pd.to_numeric(result_df['漲跌幅'].astype(str).str.replace('%', ''), errors='coerce').fillna(0)
    
    result_df['買超占比%'] = ((result_df['法人買賣超'] / 5) / (result_df['今日成交量'] / 1000) * 100).round(2)
    result_df['乖離%'] = ((result_df['股票股價'] - result_df['主力5日成本']) / result_df['主力5日成本'] * 100).round(2)

    # 評分邏輯
    max_p = result_df['籌碼力道'].max()
    result_df['力道分數'] = (result_df['籌碼力道'] / max_p * 45).round(2) if max_p > 0 else 0
    max_ratio = result_df['買超占比%'].max()
    result_df['占比分數'] = (result_df['買超占比%'] / max_ratio * 40).round(2) if max_ratio > 0 else 0
    result_df['距離分數'] = result_df['乖離%'].apply(lambda x: max(0, 15 - abs(x))).round(2)
    result_df['個股分數'] = result_df['力道分數'] + result_df['占比分數'] + result_df['距離分數']
    result_df['發動狀態'] = result_df.apply(get_bottom_status_v2, axis=1)

    status_mapping = {"🔥 底部起漲": 1, "💎 鎖碼盤整": 2, "🔎 觀察中": 3, "⚠️ 高檔轉弱 (避開)": 4, "📉 趨勢轉空": 5}
    result_df['狀態等級'] = result_df['發動狀態'].map(status_mapping)
    return result_df.sort_values(by=['狀態等級', '個股分數'], ascending=[True, False]).head(15).reset_index(drop=True)

# --- 3. Streamlit UI 介面 ---

st.set_page_config(page_title="AI 籌碼戰情室", layout="wide")

st.markdown("# Chips of TW Stock Analysis System")
st.markdown("###### reference : [CMoney](https://www.cmoney.tw/) * [data](https://www.cmoney.tw/forum/stock/rank/institutional-investor-buy?period=week) -- Date:" f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")


def fetch_stock_name_from_cmoney(ticker):
    """ 從 CMoney 現場精準抓取名稱 """
    url = f"https://www.cmoney.tw/forum/stock/{ticker}"
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 鎖定 span.stockData__name
            name_tag = soup.select_one('span.stockData__name')
            if name_tag:
                return name_tag.text.strip()
        return None
    except:
        return None


def fetch_stock_info_from_cmoney(ticker):
    """ 從 CMoney 現場抓取名稱並直接計算 3 日法人買賣超加總 """
    url = f"https://www.cmoney.tw/forum/stock/{ticker}?s=institutional"
    info = {"name": None, "inst_buy": "查無數據"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            name_tag = soup.select_one('span.stockData__name')
            if name_tag:
                info["name"] = name_tag.text.strip()
            
            cells = soup.select('td.table__three')
            if cells:
                total_3d = sum(int(c.text.strip().replace(',', '')) for c in cells[:3] if c.text.strip().replace(',', '').replace('-', '').isdigit())
                info["inst_buy"] = f"{total_3d:,} 張"
                
        return info
    except:
        return info

    
# 1. 彈出視窗函式 (名稱現在改為由外部傳入或現場顯示)
@st.dialog("📈 個股詳細戰情")
def show_stock_details(ticker, name):
    try:
        clean_ticker = str(ticker).strip()
        stock_data = yf.Ticker(f"{clean_ticker}.TW")
        hist = stock_data.history(period="5d")
        
        if hist.empty:
            stock_data = yf.Ticker(f"{clean_ticker}.TWO")
            hist = stock_data.history(period="5d")
        
        if not hist.empty:
            current_p = hist['Close'].iloc[-1]
            prev_p = hist['Close'].iloc[-2]
            diff = current_p - prev_p
            pct_change = (diff / prev_p) * 100
            
            # 顯示從 CMoney 爬來的名稱
            st.write(f"### {name} ({clean_ticker})")
            
            col_a, col_b = st.columns(2)
            col_a.metric("當前股價", f"{current_p:.2f}", f"{diff:.2f} ({pct_change:.2f}%)")
            
            
            inst_info = fetch_stock_info_from_cmoney(ticker)
            col_b.metric("法人近三日買賣超", inst_info["inst_buy"])
            st.divider()
            

            # --- Plotly 高波動走勢圖 ---
            start_price = hist['Close'].iloc[0]
            end_price = hist['Close'].iloc[-1]
            line_color = '#eb4d4b' if end_price >= start_price else '#6ab04c' 

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist.index, y=hist['Close'],
                mode='lines+markers',
                line=dict(color=line_color, width=3),
                fill='tozeroy',
                fillcolor=f'rgba({235 if end_price >= start_price else 106}, {77 if end_price >= start_price else 176}, {75 if end_price >= start_price else 76}, 0.1)'
            ))

            y_min, y_max = hist['Close'].min(), hist['Close'].max()
            padding = (y_max - y_min) * 0.05
            fig.update_layout(
                height=180, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor='rgba(200,200,200,0.1)', side="right", range=[y_min-padding, y_max+padding]),
                hovermode="x unified"
            )
            
            st.write("📊 **五日股價走勢**")
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.write(f"- [More Info](https://www.cmoney.tw/forum/stock/{clean_ticker})")
            
        else:
            st.warning(f"Yahoo Finance 暫無代號 {clean_ticker} 的報價。")
    except Exception as e:
        st.error(f"查詢失敗：{e}")

query_ticker = st.text_input("🔍 查詢個股 (輸入代號並按 Enter)", "")

if query_ticker:

    with st.spinner(f'Please wait!! 正在爬取 {query_ticker} 的資料...'):
        live_name = fetch_stock_name_from_cmoney(query_ticker)
        
        target_name = live_name if live_name else f"代號 {query_ticker}"
        
        show_stock_details(query_ticker, target_name)


st.sidebar.header("⚙️")
api_key = st.sidebar.text_input("Gemini API Key", type="password")
budget = st.sidebar.number_input("Bugets(10k)", value=100) 
pick_num = st.sidebar.slider("AI recommand stocks", 1, 8, 4)

if st.sidebar.button("🚀 Go Ahead !!"):
    if not api_key:
        st.error("Please fill up your Gemini API Key")
    else:
        final_table = run_full_analysis(budget, pick_num)
        
        if final_table is not None:
            col1, col2 = st.columns([3, 2])
            with col1:
                st.subheader("💲rank table list ")
                
                # 準備資料副本
                df_to_show = final_table[['代號','名稱','股票股價','漲跌幅','發動狀態','個股分數','買超占比%','乖離%']].copy()
                
                # --- 新增這行：將代號轉為超連結 ---
                df_to_show['代號'] = df_to_show['代號'].apply(make_clickable)
                
                def color_status(val):
                    color = 'lightgreen' if val == "🔥 底部起漲" else 'lightyellow' if val == "💎 鎖碼盤整" else 'red'
                    return f'background-color: {color}; color: black'
                
                format_dict = {
                    '股票股價': '{:.1f}',
                    '個股分數': '{:.1f}',
                    '買超占比%': '{:.1f}',
                    '乖離%': '{:.1f}'
                }
                
                # 建立 Styler
                styled_df = df_to_show.style.format(format_dict) \
                    .applymap(color_status, subset=['發動狀態']) \
                    .set_properties(**{
                        'font-size': '18px',
                        'text-align': 'center'
                    })
    
                st.write(styled_df.to_html(escape=False), unsafe_allow_html=True)

            with col2:
                st.subheader("🤖")
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('models/gemini-2.5-flash')
                    table_str = final_table[['代號','名稱','股票股價','個股分數','發動狀態','漲跌幅']].to_string(index=False)
                    prompt = f"""
                    你現在是「極簡主義財經持股建構系統」。請根據以下數據進行專業的資產配置。

                    【任務核心】
                    - 總預算：{budget} 萬台幣 (即 {budget * 10000} 元)。
                    - 選股數量：由你從數據中挑選最強的 {pick_num} 檔。
                    - 止損位：統一設定為購入價格下跌 5%。

                    【分配邏輯：效益最大化】
                    1. **動態占比**：請「不要」平均分配資金。
                    2. **加權原則**：個股分數越高、且狀態為 [🔥 底部起漲] 的股票，請分配較高的預算比例。
                    3. **計算要求**：
                       - 請為每一檔選中的股票決定一個「分配占比 (%)」。
                       - 股數 = (總預算 * 占比) / 該股股價 (取整數張或整數股)。
                       - 止損位 = 該股股價 * 0.95。

                    【輸出格式規則 - 嚴格執行】
                    - 每一檔股票必須以「- 」開頭，且「單獨成行」。
                    - 每行之間必須留一個空行，確保手機端閱讀清晰。

                    【輸出範例】
                    作為極簡主義財經系統，我們已為您優化配置如下：

                    - [2548 華固] - 分配預算: 購買 1200 股 (占比 30%, 約 147,000 元) - 觸發邏輯: [🔥 底部起漲] - 止損位: 116.4 元

                    - [2886 兆豐金] - 分配預算: 購買 4500 股 (占比 25%, 約 173,700 元) - 觸發邏輯: [💎 鎖碼盤整] - 止損位: 36.67 元

                    總計分配預算：約 X 元。

                    【待處理原始數據】
                    {table_str}
                    """
                    response = model.generate_content(prompt)
                    st.info(response.text)
                except Exception as e:
                    st.error(f"AI 生成失敗: {e}")
                    
