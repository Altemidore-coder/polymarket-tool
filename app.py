import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Master", layout="wide")

# Style Mobile & Métriques
st.markdown("""
    <style>
        .block-container { padding-top: 0.5rem; padding-left: 0.5rem; padding-right: 0.5rem; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDataFrame { font-size: 0.8rem; }
        /* Style pour les métriques colorées */
        div[data-testid="stMetricValue"] { font-size: 1.1rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Master")

# --- CONSTANTES ---
MAIN_CATEGORIES = ["Politics", "Crypto", "Sports", "Business", "Science", "Pop Culture", "News"]

# --- API ---
@st.cache_data(ttl=60)
def fetch_active_markets(limit=1000):
    """Récupère les marchés pour l'Explorateur"""
    url = "https://gamma-api.polymarket.com/events"
    params = {"limit": limit, "active": "true", "closed": "false", "order": "volume", "ascending": "false"}
    try:
        r = requests.get(url, params=params)
        return r.json()
    except: return []

def fetch_user_positions(address):
    """Récupère le portfolio brut"""
    if len(address) < 10: return []
    url = "https://data-api.polymarket.com/positions"
    params = {"user": address, "sizeThreshold": "0.1", "limit": "100"}
    try:
        r = requests.get(url, params=params)
        return r.json()
    except: return []

@st.cache_data(ttl=10)
def fetch_clob_prices():
    """Récupère tous les prix du CLOB (Mapping Asset ID -> Prix)"""
    url = "https://clob.polymarket.com/prices"
    try:
        r = requests.get(url)
        data = r.json()
        price_map = {}
        for item in data:
            if 'token_id' in item and 'price' in item:
                t_id = str(item['token_id'])
                price = float(item['price'])
                price_map[t_id] = price
        return price_map
    except: return {}

# --- CHARGEMENT ---
raw_data = fetch_active_markets()

# --- FILTRES & RÉGLAGES (RESTAURÉS) ---
with st.expander("⚙️ RÉGLAGES & COMPTE (Cliquer pour ouvrir)", expanded=False):
    st.subheader("👤 Mon Compte")
    user_address = st.text_input("Adresse Polygon (0x...)", value="", help="Adresse Proxy")
    
    st.divider()
    
    st.subheader("🔍 Filtres Marché")
    c1, c2 = st.columns(2)
    with c1:
        max_days = st.slider("Jours Max", 0, 60, 7)
        min_vol = st.number_input("Volume Min ($)", value=1000, step=1000)
    with c2:
        min_liquidity = st.number_input("Liq. Min ($)", value=100, step=100)
        exclude_bots = st.checkbox("Masquer Bots 'Up/Down'", value=True)
    
    # Catégories dynamiques
    found_cats = set()
    for item in raw_data:
        tags = item.get('tags', [])
        for t in tags:
            if t.get('label'): found_cats.add(t.get('label'))
    all_cats = sorted(list(set(MAIN_CATEGORIES + list(found_cats))))
    selected_cats = st.multiselect("Thèmes", all_cats, default=[c for c in MAIN_CATEGORIES if c in all_cats])

    if st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["🌎 EXPLORATEUR", "💼 PORTFOLIO"])

# --- ONGLET 1 : EXPLORATEUR (COMPLET) ---
with tab1:
    explorer_list = []
    if raw_data:
        for item in raw_data:
            if not item.get('markets'): continue
            
            # 1. Filtre Anti-Bot
            title = item.get('title', '').lower()
            if exclude_bots and ("up or down" in title or "up/down" in title or "15min" in title): continue
            
            # 2. Filtre Catégorie
            tags = [t.get('label') for t in item.get('tags', []) if t.get('label')]
            cat = "Autre"
            for m_cat in MAIN_CATEGORIES:
                if m_cat in tags:
                    cat = m_cat
                    break
            if not cat in MAIN_CATEGORIES and tags: cat = tags[0]
            if cat not in selected_cats: continue

            # 3. Temps
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

            # 4. Application stricte des filtres
            if (hours_left <= (max_days * 24)) and (liq >= min_liquidity) and (vol >= min_vol):
                explorer_list.append({
                    "Info": cat, "Titre": item.get('title'), "Prix": p_yes,
                    "Vol.": vol, "Liq.": liq, "Temps": time_lbl, "Sort": hours_left,
                    "Lien": f"https://polymarket.com/event/{item.get('slug')}"
                })
        
        df_exp = pd.DataFrame(explorer_list)
        if not df_exp.empty:
            st.caption(f"{len(df_exp)} opportunités trouvées")
            st.dataframe(
                df_exp.sort_values(by="Sort").drop(columns=["Sort"]), 
                column_config={
                    "Lien": st.column_config.LinkColumn("Go"),
                    "Prix": st.column_config.ProgressColumn("Prix", format="%.2f", min_value=0, max_value=1),
                    "Vol.": st.column_config.NumberColumn(format="$%d"),
                    "Liq.": st.column_config.NumberColumn(format="$%d"),
                },
                use_container_width=True, hide_index=True
            )
        else: st.info("Aucun marché ne correspond à tes filtres.")

# --- ONGLET 2 : PORTFOLIO (AVEC RÉSUMÉ) ---
with tab2:
    if not user_address:
        st.warning("Entre ton adresse dans les réglages.")
    else:
        with st.spinner("Analyse financière..."):
            positions = fetch_user_positions(user_address)
            clob_prices = fetch_clob_prices() 
            
            if positions:
                my_pos = []
                # Totaux pour le résumé
                total_invested = 0
                total_current_value = 0
                
                for p in positions:
                    size = float(p.get('size', 0))
                    if size < 0.1: continue
                    
                    asset_decimal = str(p.get('asset'))
                    title = p.get('title', 'Inconnu')
                    side_label = p.get('outcome', 'OUI')
                    
                    # Prix moyen d'achat
                    avg_price = float(p.get('avgPrice', 0))
                    
                    # LOGIQUE PRIX (La tienne qui marche !)
                    current_price = 0
                    if asset_decimal in clob_prices:
                        current_price = clob_prices[asset_decimal]
                    
                    if current_price == 0:
                        try:
                            asset_hex = hex(int(asset_decimal))
                            if asset_hex in clob_prices:
                                current_price = clob_prices[asset_hex]
                        except: pass
                    
                    if current_price == 0:
                        current_price = float(p.get('curPrice', 0))

                    # Calculs Ligne
                    invested = size * avg_price
                    val = size * current_price
                    
                    # Ajout aux totaux globaux
                    total_invested += invested
                    total_current_value += val
                    
                    pnl_pct = 0
                    if avg_price > 0:
                        pnl_pct = ((current_price - avg_price) / avg_price) * 100

                    my_pos.append({
                        "Marché": title,
                        "Côté": side_label,
                        "Parts": size,
                        "Achat": avg_price,
                        "Actuel": current_price,
                        "Investi": invested,
                        "Valeur": val,
                        "PnL": pnl_pct
                    })
                
                if my_pos:
                    # --- NOUVEAU : LE RÉSUMÉ FINANCIER ---
                    total_pnl_usd = total_current_value - total_invested
                    total_pnl_pct = (total_pnl_usd / total_invested * 100) if total_invested > 0 else 0
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Investi", f"${total_invested:,.2f}")
                    c2.metric("Valeur Actuelle", f"${total_current_value:,.2f}")
                    c3.metric("Profit / Perte", f"${total_pnl_usd:+,.2f}", f"{total_pnl_pct:+.2f}%")
                    
                    st.divider()

                    # Tableau
                    df_pos = pd.DataFrame(my_pos).sort_values(by="Valeur", ascending=False)
                    st.dataframe(
                        df_pos,
                        column_config={
                            "Marché": st.column_config.TextColumn(width="medium"),
                            "Parts": st.column_config.NumberColumn(format="%.1f"),
                            "Achat": st.column_config.NumberColumn(format="%.3f"),
                            "Actuel": st.column_config.NumberColumn(format="%.3f"),
                            "Investi": st.column_config.NumberColumn(format="$%.2f"),
                            "Valeur": st.column_config.NumberColumn(format="$%.2f"),
                            "PnL": st.column_config.NumberColumn("Profit %", format="%.1f%%"),
                        },
                        use_container_width=True, hide_index=True
                    )
                else: st.info("Portefeuille vide.")
            else: st.error("Impossible de récupérer le portfolio.")