import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Pro", layout="wide")
st.markdown("""
    <style>
        .block-container { padding-top: 0.5rem; padding-left: 0.5rem; padding-right: 0.5rem; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDataFrame { font-size: 0.8rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Pro")

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
    # On récupère les positions
    url = "https://data-api.polymarket.com/positions"
    params = {"user": address, "sizeThreshold": "0.1", "limit": "100"}
    try:
        r = requests.get(url, params=params)
        return r.json()
    except: return []

@st.cache_data(ttl=10) # Cache court (10s) pour avoir le prix frais
def fetch_clob_prices():
    """Récupère TOUS les prix du carnet d'ordre central par Token ID"""
    url = "https://clob.polymarket.com/prices"
    try:
        r = requests.get(url)
        data = r.json()
        # On transforme la liste en dictionnaire : { "0xTokenID...": 0.65 }
        price_map = {}
        for item in data:
            if 'token_id' in item and 'price' in item:
                price_map[item['token_id']] = float(item['price'])
        return price_map
    except: return {}

# --- INIT ---
raw_data = fetch_active_markets()

# --- REGLAGES ---
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
    
    # Debug Switch
    debug_mode = st.checkbox("🔧 Mode Debug (Afficher les données brutes)", value=False)

    if st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["🌎 EXPLORATEUR", "💼 PORTFOLIO"])

# --- ONGLET 1 : EXPLORATEUR ---
with tab1:
    explorer_list = []
    if raw_data:
        for item in raw_data:
            if not item.get('markets'): continue
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

# --- ONGLET 2 : PORTFOLIO (ASSET ID MATCHING) ---
with tab2:
    if not user_address:
        st.warning("Entre ton adresse dans les réglages.")
    else:
        with st.spinner("Synchronisation CLOB..."):
            positions = fetch_user_positions(user_address)
            # On charge TOUS les prix du marché (c'est très léger)
            clob_prices = fetch_clob_prices() 
            
            if positions:
                my_pos = []
                total_equity = 0
                
                for p in positions:
                    size = float(p.get('size', 0))
                    if size < 0.1: continue
                    
                    # C'EST ICI QUE CA SE JOUE : L'ASSET ID
                    asset_id = p.get('asset')
                    
                    title = p.get('title', 'Inconnu')
                    side_idx = int(p.get('outcomeIndex', 0))
                    side_label = "OUI" if side_idx == 0 else "NON"
                    avg_price = float(p.get('avgPrice', 0))
                    
                    # 1. On cherche l'Asset ID dans le dictionnaire CLOB
                    current_price = 0
                    source = "API"
                    
                    if asset_id in clob_prices:
                        current_price = clob_prices[asset_id]
                        source = "CLOB" # Victoire !
                    
                    # 2. Fallback
                    if current_price == 0:
                        current_price = float(p.get('currentPrice', 0))
                        source = "Old"

                    val = size * current_price
                    total_equity += val
                    pnl = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0

                    my_pos.append({
                        "Marché": title,
                        "Côté": side_label,
                        "Parts": size,
                        "Achat": avg_price,
                        "Actuel": current_price,
                        "Valeur": val,
                        "PnL": pnl,
                        "Src": source
                    })
                
                if my_pos:
                    st.metric("Valeur Totale", f"${total_equity:,.2f}")
                    df_pos = pd.DataFrame(my_pos).sort_values(by="Valeur", ascending=False)
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
                else: st.info("Aucune position active.")
                
                # --- ZONE DE DEBUG ---
                if debug_mode and len(positions) > 0:
                    st.divider()
                    st.write("### 🔧 DONNÉES BRUTES (Pour débogage)")
                    st.write("Voici à quoi ressemble ta première position. Cherche le champ 'asset'.")
                    st.json(positions[0])
                    st.write("Exemple de prix CLOB chargés :")
                    # On affiche 3 exemples de clés CLOB pour comparer
                    keys_sample = list(clob_prices.keys())[:3]
                    st.write(keys_sample)
                    
            else: st.error("Impossible de récupérer le portfolio.")