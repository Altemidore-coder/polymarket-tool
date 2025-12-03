
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Polymarket Master", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 0.5rem; padding-bottom: 0rem; padding-left: 0.5rem; padding-right: 0.5rem; }
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

# --- FONCTIONS API ---

@st.cache_data(ttl=60)
def fetch_active_markets(limit=1000):
    """Pour l'Explorer : Récupère les marchés les plus actifs"""
    url = "https://gamma-api.polymarket.com/events"
    params = {"limit": limit, "active": "true", "closed": "false", "order": "volume", "ascending": "false"}
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except: return []

def fetch_user_positions(address):
    """Pour le Portfolio : Récupère les positions brutes"""
    if len(address) < 10: return []
    url = "https://data-api.polymarket.com/positions"
    params = {"user": address, "sizeThreshold": "0.1", "limit": "100"}
    try:
        r = requests.get(url, params=params)
        return r.json()
    except: return []

def fetch_specific_markets(id_list):
    """
    SNIPER : Récupère les infos en direct pour une liste précise d'IDs.
    Gère le découpage par paquets (batching) pour ne pas casser l'URL.
    """
    if not id_list: return {}
    
    # On enlève les doublons et les valeurs vides
    clean_ids = list(set([x for x in id_list if x]))
    
    price_map = {}
    base_url = "https://gamma-api.polymarket.com/markets"
    
    # On procède par paquets de 20 IDs pour éviter les erreurs d'URL trop longue
    batch_size = 20
    for i in range(0, len(clean_ids), batch_size):
        batch = clean_ids[i:i + batch_size]
        # On construit la requête ?id=1&id=2&id=3...
        query_string = "&".join([f"id={mid}" for mid in batch])
        full_url = f"{base_url}?{query_string}"
        
        try:
            r = requests.get(full_url)
            data = r.json()
            # On stocke le résultat : ID -> [PrixYes, PrixNo]
            for m in data:
                try:
                    prices = json.loads(m.get('outcomePrices', '["0","0"]'))
                    price_map[m['id']] = prices
                except: pass
        except: pass
        
    return price_map

# --- INITIALISATION ---
raw_data = fetch_active_markets()

# --- UI: RÉGLAGES ---
with st.expander("⚙️ RÉGLAGES & COMPTE", expanded=False):
    st.subheader("👤 Mon Compte")
    user_address = st.text_input("Adresse Polygon (0x...)", value="", help="Adresse Proxy ou EOA")
    
    st.divider()
    
    st.subheader("🔍 Filtres Explorer")
    c1, c2 = st.columns(2)
    with c1:
        max_days = st.slider("Jours Max", 0, 60, 7)
        min_vol = st.number_input("Volume Min ($)", value=1000, step=1000)
    with c2:
        min_liquidity = st.number_input("Liq. Min ($)", value=100, step=100)
        exclude_bots = st.checkbox("Masquer Bots", value=True)
    
    # Catégories dynamiques
    found_cats = set()
    for item in raw_data:
        tags = item.get('tags', [])
        for t in tags:
            if t.get('label'): found_cats.add(t.get('label'))
    all_cats = sorted(list(set(MAIN_CATEGORIES + list(found_cats))))
    selected_cats = st.multiselect("Thèmes", all_cats, default=[c for c in MAIN_CATEGORIES if c in all_cats])

    if st.button("🔄 Rafraîchir tout"):
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
            
            title = item.get('title', '').lower()
            if exclude_bots and ("up or down" in title or "up/down" in title or "15min" in title): continue
            
            tags = [t.get('label') for t in item.get('tags', []) if t.get('label')]
            cat = "Autre"
            for m_cat in MAIN_CATEGORIES:
                if m_cat in tags:
                    cat = m_cat
                    break
            if not cat in MAIN_CATEGORIES and tags: cat = tags[0]
            if cat not in selected_cats: continue

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

            if (hours_left <= (max_days * 24)) and (liq >= min_liquidity) and (vol >= min_vol):
                explorer_list.append({
                    "Info": cat,
                    "Titre": item.get('title'),
                    "Prix": p_yes,
                    "Vol.": vol,
                    "Liq.": liq,
                    "Temps": time_lbl,
                    "Sort": hours_left,
                    "Lien": f"https://polymarket.com/event/{item.get('slug')}"
                })
        
        df_exp = pd.DataFrame(explorer_list)
        if not df_exp.empty:
            df_exp = df_exp.sort_values(by="Sort", ascending=True)
            st.dataframe(
                df_exp.drop(columns=["Sort"]),
                column_config={
                    "Lien": st.column_config.LinkColumn("Go"),
                    "Prix": st.column_config.ProgressColumn("Prix", format="%.2f", min_value=0, max_value=1),
                    "Vol.": st.column_config.NumberColumn(format="$%d"),
                    "Liq.": st.column_config.NumberColumn(format="$%d"),
                },
                use_container_width=True,
                hide_index=True
            )
        else: st.info("Aucun marché trouvé.")

# --- ONGLET 2 : PORTFOLIO (TARGETED FETCH) ---
with tab2:
    if not user_address:
        st.warning("⚠️ Entre ton adresse dans 'Réglages'.")
    else:
        with st.spinner("Analyse approfondie du portefeuille..."):
            positions = fetch_user_positions(user_address)
            
            if positions:
                # 1. Extraction des IDs de tes marchés
                my_market_ids = [p.get('market') for p in positions if p.get('market')]
                
                # 2. APPEL SNIPER : On va chercher les prix JUSTE pour ces marchés
                sniper_prices = fetch_specific_markets(my_market_ids)
                
                my_pos = []
                total_equity = 0
                
                for p in positions:
                    size = float(p.get('size', 0))
                    if size < 0.1: continue
                    
                    market_id = p.get('market') # L'ID précis
                    title = p.get('title', 'Inconnu')
                    
                    side_idx = int(p.get('outcomeIndex', 0))
                    side_label = "OUI" if side_idx == 0 else "NON"
                    avg_price = float(p.get('avgPrice', 0))
                    
                    # --- LOGIQUE DE PRIX ---
                    current_price = 0
                    source = "API"
                    
                    # A. On cherche dans le Sniper (Priorité absolue)
                    if market_id in sniper_prices:
                        try:
                            # On récupère le prix OUI ou NON selon ta position
                            current_price = float(sniper_prices[market_id][side_idx])
                            source = "Sniper"
                        except: pass
                    
                    # B. Fallback : Si le sniper a raté (marché fermé?), on prend le vieux prix
                    if current_price == 0:
                        current_price = float(p.get('currentPrice', 0))
                        source = "Old"

                    val = size * current_price
                    total_equity += val
                    
                    pnl = 0
                    if avg_price > 0:
                        pnl = ((current_price - avg_price) / avg_price) * 100

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
                
                df_pos = pd.DataFrame(my_pos)
                
                if not df_pos.empty:
                    st.metric("Valeur Portefeuille", f"${total_equity:,.2f}")

		    df_pos = df_pos.sort_values(by="Valeur", ascending=False)
                    
                    st.dataframe(
                        df_pos,
                        column_config={
                            "Marché": st.column_config.TextColumn(width="medium"),
                            "Parts": st.column_config.NumberColumn(format="%.1f"),
                            "Achat": st.column_config.NumberColumn(format="%.3f"),
                            "Actuel": st.column_config.NumberColumn(format="%.3f"),
                            "Valeur": st.column_config.NumberColumn(format="$%.2f"),
                            "PnL": st.column_config.NumberColumn("Profit %", format="%.1f%%"),
                            "Src": st.column_config.TextColumn("Src", help="Sniper = Prix frais en direct")
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else: st.info("Aucune position active.")
            else: st.error("Impossible de récupérer les positions.")