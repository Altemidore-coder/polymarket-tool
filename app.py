
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Tracker", layout="wide")

# --- STYLE MOBILE & UI ---
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 0.5rem; padding-right: 0.5rem; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDataFrame { font-size: 0.8rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Tracker")

# --- CONSTANTES ---
MAIN_CATEGORIES = ["Politics", "Crypto", "Sports", "Business", "Science", "Pop Culture"]

# --- FONCTIONS API ---

@st.cache_data(ttl=60)
def fetch_markets(limit=1000):
    """Récupère les marchés généraux pour l'explorateur"""
    url = "https://gamma-api.polymarket.com/events"
    params = {"limit": limit, "active": "true", "closed": "false", "order": "endDate", "ascending": "true"}
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except: return []

def fetch_user_positions(address):
    """Récupère les positions brutes de l'utilisateur (Data API)"""
    if len(address) < 40: return []
    url = "https://data-api.polymarket.com/positions"
    params = {"user": address, "sizeThreshold": "0.1", "limit": "50"} # On ignore les poussières
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Erreur Portfolio: {e}")
        return []

def fetch_specific_prices(market_ids):
    """NOUVEAU : Récupère les prix en direct pour une liste d'IDs précis"""
    if not market_ids: return {}
    
    # On nettoie la liste et on limite à 50 pour ne pas casser l'URL
    clean_ids = list(set(market_ids))[:50]
    
    # On construit une requête : ?id=123&id=456...
    query_params = [f"id={mid}" for mid in clean_ids]
    query_string = "&".join(query_params)
    
    url = f"https://gamma-api.polymarket.com/markets?{query_string}"
    
    try:
        r = requests.get(url)
        data = r.json()
        
        # On crée un dictionnaire propre : ID -> [PrixYes, PrixNo]
        price_map = {}
        for m in data:
            try:
                prices = json.loads(m.get('outcomePrices', '["0","0"]'))
                price_map[m['id']] = prices # Ex: ["0.65", "0.35"]
            except: pass
        return price_map
    except: return {}

# --- CHARGEMENT DONNÉES GLOBALES ---
raw_data = fetch_markets()

# --- BARRE DE RÉGLAGES ---
with st.expander("⚙️ RÉGLAGES & COMPTE", expanded=True):
    st.write("### 👤 Mon Compte")
    user_address = st.text_input("Adresse Polygon (0x...)", help="Adresse publique Metamask/Proxy")
    
    st.divider()
    
    st.write("### 🔍 Filtres Marché")
    c1, c2 = st.columns(2)
    with c1:
        max_days = st.slider("Jours Max", 0, 30, 7)
        only_rewards = st.checkbox("💰 Avec Rewards LP", value=False)
    with c2:
        min_liquidity = st.number_input("Liq. Min ($)", value=100, step=100)
        exclude_up_down = st.checkbox("Masquer Bots", value=True)

    st.write("📂 Catégories")
    all_found_cats = set()
    for item in raw_data:
        tags = item.get('tags', [])
        for t in tags:
            if t.get('label'): all_found_cats.add(t.get('label'))
    options = sorted(list(set(MAIN_CATEGORIES + list(all_found_cats))))
    selected_cats = st.multiselect("Thèmes", options, default=[c for c in MAIN_CATEGORIES if c in options])

    if st.button("🔄 Actualiser"):
        st.cache_data.clear()
        st.rerun()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["🌎 EXPLORATEUR", "💼 MON PORTFOLIO"])

# --- ONGLET 1 : EXPLORATEUR ---
with tab1:
    market_list = []
    if raw_data:
        for item in raw_data:
            if not item.get('markets'): continue
            
            # Filtres
            if only_rewards and (not item.get('rewards') or len(item.get('rewards', [])) == 0): continue
            
            title = item.get('title', '').lower()
            if exclude_up_down and ("up or down" in title or "up/down" in title or "15min" in title): continue

            # Catégorie
            tags_raw = item.get('tags', [])
            market_category = "Autre"
            current_tags = [t.get('label') for t in tags_raw if t.get('label')]
            found_main = False
            for main_cat in MAIN_CATEGORIES:
                if main_cat in current_tags:
                    market_category = main_cat
                    found_main = True
                    break
            if not found_main and current_tags: market_category = current_tags[0]
            if market_category not in selected_cats: continue

            m = item['markets'][0]
            
            # Temps
            end_date_str = item.get('endDate')
            hours_left = 9999
            time_display = "N/A"
            if end_date_str:
                try:
                    end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    now = datetime.now(end_dt.tzinfo)
                    total_seconds = (end_dt - now).total_seconds()
                    if total_seconds <= 0: continue
                    hours_left = total_seconds / 3600
                    days_left = hours_left / 24
                    if days_left < 1: time_display = f"{int(hours_left)}h 🔥"
                    else: time_display = f"{int(days_left)}j"
                except: pass

            try:
                prices = json.loads(m.get('outcomePrices', '["0","0"]'))
                price_yes = float(prices[0])
            except: price_yes = 0

            liq = float(m.get('liquidity', 0) or 0)
            vol = float(item.get('volume', 0) or 0)
            
            rewards_badge = "🎁" if item.get('rewards') else ""

            if (hours_left <= (max_days * 24)) and (liq >= min_liquidity):
                market_list.append({
                    "Info": f"{market_category} {rewards_badge}",
                    "Titre": item.get('title'),
                    "Temps": time_display,
                    "Prix": price_yes,
                    "Liq.": liq,
                    "Sort": hours_left,
                    "Lien": f"https://polymarket.com/event/{item.get('slug')}"
                })

        df = pd.DataFrame(market_list)
        if not df.empty:
            df = df.sort_values(by="Sort", ascending=True)
            st.dataframe(
                df.drop(columns=["Sort"]),
                column_config={
                    "Lien": st.column_config.LinkColumn("Go"),
                    "Prix": st.column_config.ProgressColumn("Prix", format="%.2f", min_value=0, max_value=1),
                    "Liq.": st.column_config.NumberColumn(format="$%d"),
                },
                use_container_width=True,
                hide_index=True
            )
        else: st.info("Aucun marché trouvé.")

# --- ONGLET 2 : PORTFOLIO (FIX PRIX) ---
with tab2:
    if not user_address:
        st.warning("⚠️ Entre ton adresse Polygon ci-dessus.")
    else:
        with st.spinner("Analyse du portfolio..."):
            positions_data = fetch_user_positions(user_address)
            
            if positions_data:
                # 1. On récupère la liste des IDs de marchés de tes positions
                my_market_ids = [p.get('market') for p in positions_data if p.get('market')]
                
                # 2. APPEL API CIBLÉ : On demande les prix pour ces marchés précis
                real_time_prices = fetch_specific_prices(my_market_ids)
                
                my_pos = []
                total_value = 0
                
                for p in positions_data:
                    size = float(p.get('size', 0))
                    if size < 0.1: continue 
                    
                    market_id = p.get('market')
                    title = p.get('title', 'Inconnu')
                    outcome_idx = int(p.get('outcomeIndex', 0)) # 0 ou 1
                    outcome_label = "OUI" if outcome_idx == 0 else "NON"
                    avg_price = float(p.get('avgPrice', 0))
                    
                    # 3. On va chercher le prix dans notre nouveau dictionnaire frais
                    current_price = 0
                    if market_id in real_time_prices:
                        try:
                            prices_list = real_time_prices[market_id]
                            current_price = float(prices_list[outcome_idx])
                        except: pass
                    
                    # Fallback : Si l'API échoue, on prend le prix estimé (souvent faux mais mieux que 0)
                    if current_price == 0:
                        current_price = float(p.get('currentPrice', 0))

                    # Calculs
                    val = size * current_price
                    total_value += val
                    pnl = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0

                    my_pos.append({
                        "Marché": title,
                        "Côté": outcome_label,
                        "Parts": size,
                        "Achat": avg_price,
                        "Actuel": current_price,
                        "Valeur": val,
                        "PnL": pnl,
                        "Sort_PnL": pnl
                    })

                df_pos = pd.DataFrame(my_pos)
                if not df_pos.empty:
                    st.metric("Valeur Totale", f"${total_value:,.2f}")
                    df_pos = df_pos.sort_values(by="Sort_PnL", ascending=False)
                    st.dataframe(
                        df_pos.drop(columns=["Sort_PnL"]),
                        column_config={
                            "Marché": st.column_config.TextColumn("Marché", width="medium"),
                            "Parts": st.column_config.NumberColumn(format="%.1f"),
                            "Achat": st.column_config.NumberColumn(format="%.3f"),
                            "Actuel": st.column_config.NumberColumn(format="%.3f"),
                            "Valeur": st.column_config.NumberColumn(format="$%.2f"),
                            "PnL": st.column_config.NumberColumn("Profit %", format="%.1f%%")
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else: st.info("Aucune position active.")
            else: st.info("Portefeuille vide ou adresse incorrecte.")