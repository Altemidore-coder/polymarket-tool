import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Master", layout="wide")
st.markdown("""
    <style>
        .block-container { padding-top: 0.5rem; padding-left: 0.5rem; padding-right: 0.5rem; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDataFrame { font-size: 0.8rem; }
        div[data-testid="stMetricValue"] { font-size: 1.2rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Master")

# --- CONSTANTES ---
MAIN_CATEGORIES = ["Politics", "Crypto", "Sports", "Business", "Science", "Pop Culture"]

# --- API ---
@st.cache_data(ttl=60)
def fetch_active_markets(limit=1000):
    url = "https://gamma-api.polymarket.com/events"
    params = {"limit": limit, "active": "true", "closed": "false", "order": "volume", "ascending": "false"}
    try:
        r = requests.get(url, params=params)
        return r.json()
    except: return []

def fetch_user_positions(address):
    if len(address) < 10: return []
    url = "https://data-api.polymarket.com/positions"
    params = {"user": address, "sizeThreshold": "0.1", "limit": "100"}
    try:
        r = requests.get(url, params=params)
        return r.json()
    except: return []

@st.cache_data(ttl=10)
def fetch_clob_prices():
    """Récupère les prix du CLOB et prépare les clés en format DECIMAL et HEXA"""
    url = "https://clob.polymarket.com/prices"
    try:
        r = requests.get(url)
        data = r.json()
        price_map = {}
        for item in data:
            if 'token_id' in item and 'price' in item:
                # On stocke l'ID tel quel (souvent String d'un entier énorme)
                t_id = str(item['token_id'])
                price = float(item['price'])
                price_map[t_id] = price
        return price_map
    except: return {}

# --- INIT ---
raw_data = fetch_active_markets()

# --- RÉGLAGES ---
with st.expander("⚙️ RÉGLAGES & COMPTE", expanded=False):
    st.subheader("👤 Mon Compte")
    user_address = st.text_input("Adresse Polygon (0x...)", value="", help="Adresse Proxy")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        max_days = st.slider("Jours Max", 0, 60, 7)
    with c2:
        min_liquidity = st.number_input("Liq. Min ($)", value=100)
        exclude_bots = st.checkbox("Masquer Bots", value=True)
    
    if st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["🌎 EXPLORATEUR", "💼 MON PORTFOLIO"])

# --- ONGLET 1 : EXPLORATEUR ---
with tab1:
    explorer_list = []
    if raw_data:
        for item in raw_data:
            if not item.get('markets'): continue
            
            # Filtres
            title = item.get('title', '').lower()
            if exclude_bots and ("up or down" in title or "up/down" in title or "15min" in title): continue
            
            tags = [t.get('label') for t in item.get('tags', []) if t.get('label')]
            cat = "Autre"
            for m_cat in MAIN_CATEGORIES:
                if m_cat in tags:
                    cat = m_cat
                    break
            
            end_str = item.get('endDate')
            hours_left = 9999
            time_lbl = "N/A"
            if end_str:
                try:
                    dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    diff = (dt - datetime.now(dt.tzinfo)).total_seconds()
                    if diff <= 0: continue
                    hours_left = diff / 3600
                    if hours_left < 24: time_lbl = f"{int(hours_left)}h 🔥"
                    else: time_lbl = f"{int(hours_left/24)}j"
                except: pass

            m = item['markets'][0]
            liq = float(m.get('liquidity', 0) or 0)
            vol = float(item.get('volume', 0) or 0)
            try:
                prices = json.loads(m.get('outcomePrices', '["0","0"]'))
                p_yes = float(prices[0])
            except: p_yes = 0

            if (hours_left <= (max_days * 24)) and (liq >= min_liquidity):
                explorer_list.append({
                    "Info": cat, "Titre": item.get('title'), "Prix": p_yes,
                    "Vol.": vol, "Liq.": liq, "Temps": time_lbl, "Sort": hours_left,
                    "Lien": f"https://polymarket.com/event/{item.get('slug')}"
                })
        
        df_exp = pd.DataFrame(explorer_list)
        if not df_exp.empty:
            st.dataframe(df_exp.sort_values(by="Sort").drop(columns=["Sort"]), use_container_width=True, hide_index=True)
        else: st.info("Aucun marché.")

# --- ONGLET 2 : PORTFOLIO (FIX DEFINITIF) ---
with tab2:
    if not user_address:
        st.warning("Entre ton adresse ci-dessus.")
    else:
        with st.spinner("Calcul des profits..."):
            positions = fetch_user_positions(user_address)
            clob_prices = fetch_clob_prices() 
            
            if positions:
                my_pos = []
                total_equity = 0
                
                for p in positions:
                    size = float(p.get('size', 0))
                    if size < 0.1: continue
                    
                    # 1. RECUPERATION DONNEES JSON
                    asset_decimal = str(p.get('asset')) # Le grand nombre "1597..."
                    title = p.get('title', 'Inconnu')
                    side_label = p.get('outcome', 'OUI') # "Yes" dans ton JSON
                    avg_price = float(p.get('avgPrice', 0))
                    
                    # 2. LOGIQUE DE PRIX (TRIPLE VERROUILLAGE)
                    current_price = 0
                    source = "-"
                    
                    # Tentative A : Match direct Décimal (Asset ID)
                    if asset_decimal in clob_prices:
                        current_price = clob_prices[asset_decimal]
                        source = "CLOB"
                    
                    # Tentative B : Conversion en Hexadécimal (Asset ID -> Hex)
                    if current_price == 0:
                        try:
                            asset_hex = hex(int(asset_decimal)) # Convertit 1597... en 0x235...
                            if asset_hex in clob_prices:
                                current_price = clob_prices[asset_hex]
                                source = "CLOB(Hex)"
                        except: pass
                    
                    # Tentative C : Fallback sur le JSON (CORRIGÉ : on utilise 'curPrice' et non 'currentPrice')
                    if current_price == 0:
                        current_price = float(p.get('curPrice', 0)) # <--- LA CORRECTION EST ICI
                        source = "API"

                    # 3. CALCULS
                    val = size * current_price
                    total_equity += val
                    
                    pnl_pct = 0
                    if avg_price > 0:
                        pnl_pct = ((current_price - avg_price) / avg_price) * 100

                    my_pos.append({
                        "Marché": title,
                        "Côté": side_label,
                        "Parts": size,
                        "Achat": avg_price,
                        "Actuel": current_price,
                        "Valeur": val,
                        "PnL": pnl_pct,
                        "Src": source
                    })
                
                if my_pos:
                    st.metric("Valeur Totale", f"${total_equity:,.2f}")
                    df_pos = pd.DataFrame(my_pos).sort_values(by="Valeur", ascending=False)
                    
                    # Coloriage conditionnel simple pour PnL
                    st.dataframe(
                        df_pos,
                        column_config={
                            "Marché": st.column_config.TextColumn(width="medium"),
                            "Parts": st.column_config.NumberColumn(format="%.1f"),
                            "Achat": st.column_config.NumberColumn(format="%.3f"),
                            "Actuel": st.column_config.NumberColumn(format="%.3f"),
                            "Valeur": st.column_config.NumberColumn(format="$%.2f"),
                            "PnL": st.column_config.NumberColumn("Profit %", format="%.1f%%"),
                        },
                        use_container_width=True, hide_index=True
                    )
                else: st.info("Portefeuille vide.")
            else: st.error("Impossible de lire les positions.")