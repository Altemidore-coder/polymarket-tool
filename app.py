
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Tracker", layout="wide")

# --- STYLE ---
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 0.5rem; padding-right: 0.5rem; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDataFrame { font-size: 0.8rem; }
        /* Style pour les onglets */
        .stTabs [data-baseweb="tab-list"] { gap: 2px; }
        .stTabs [data-baseweb="tab"] { padding-right: 10px; padding-left: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Tracker")

# --- CONSTANTES ---
MAIN_CATEGORIES = ["Politics", "Crypto", "Sports", "Business", "Science", "Pop Culture"]

# --- FONCTION API MARCHÉS ---
@st.cache_data(ttl=60)
def fetch_markets(limit=1000):
    url = "https://gamma-api.polymarket.com/events"
    params = {"limit": limit, "active": "true", "closed": "false", "order": "endDate", "ascending": "true"}
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except: return []

# --- FONCTION API PORTFOLIO (CORRIGÉE) ---
def fetch_user_positions(address):
    if len(address) < 40: return []
    
    # ⚠️ CHANGEMENT IMPORTANT : On utilise 'data-api' au lieu de 'gamma-api'
    url = "https://data-api.polymarket.com/positions"
    
    params = {
        "user": address,
        "sizeThreshold": "0.1", # Ignore les poussières (positions < 0.1 part)
        "limit": "50"
    }
    
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        # On affiche l'erreur dans la console pour t'aider à débugger si besoin
        print(f"Erreur Portfolio : {e}") 
        return []

# --- INIT DATA ---
raw_data = fetch_markets()

# --- BARRE DE RÉGLAGES (ACCORDÉON) ---
with st.expander("⚙️ RÉGLAGES & COMPTE", expanded=True): # Ouvert par défaut pour la première fois
    
    # 1. SECTION COMPTE
    st.write("### 👤 Mon Compte")
    user_address = st.text_input("Adresse Polygon (0x...)", help="Colle ton adresse publique ici pour voir tes positions.")
    
    st.divider()
    
    # 2. SECTION FILTRES MARCHÉ
    st.write("### 🔍 Filtres Marché")
    c1, c2 = st.columns(2)
    with c1:
        max_days = st.slider("Jours Max", 0, 30, 7)
        only_rewards = st.checkbox("💰 Avec Rewards LP", value=False, help="Ne montre que les marchés qui offrent des bonus.")
    with c2:
        min_liquidity = st.number_input("Liq. Min ($)", value=100, step=100)
        exclude_up_down = st.checkbox("Masquer Bots", value=True)

    # Catégories
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

# --- LES ONGLETS (Marchés / Mon Portfolio) ---
tab1, tab2 = st.tabs(["🌎 EXPLORATEUR", "💼 MON PORTFOLIO"])

# ==========================================
# ONGLET 1 : EXPLORATEUR DE MARCHÉS
# ==========================================
with tab1:
    market_list = []
    if raw_data:
        for item in raw_data:
            if not item.get('markets'): continue

            # Filtre Rewards LP
            if only_rewards:
                # On regarde si le champ rewards existe et n'est pas vide
                if not item.get('rewards') or len(item.get('rewards', [])) == 0:
                    continue

            # Filtre Anti-Bot
            title = item.get('title', '').lower()
            if exclude_up_down:
                if "up or down" in title or "up/down" in title or "15min" in title: continue

            # Catégories
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
            
            # Badge Rewards
            rewards_badge = ""
            if item.get('rewards'):
                rewards_badge = "🎁"

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
            display_df = df.drop(columns=["Sort"])
            st.dataframe(
                display_df,
                column_config={
                    "Lien": st.column_config.LinkColumn("Go"),
                    "Prix": st.column_config.ProgressColumn("Prix", format="%.2f", min_value=0, max_value=1),
                    "Liq.": st.column_config.NumberColumn(format="$%d"),
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucun marché trouvé.")

# ==========================================
# ONGLET 2 : MON PORTFOLIO
# ==========================================
with tab2:
    if not user_address:
        st.warning("⚠️ Entre ton adresse Polygon dans les réglages ci-dessus pour voir tes positions.")
    else:
        positions_data = fetch_user_positions(user_address)
        
        if positions_data:
            my_pos = []
            for p in positions_data:
                # On filtre les petites poussières (positions minuscules)
                size = float(p.get('size', 0))
                if size < 1: continue 
                
                title = p.get('title', 'Marché Inconnu')
                outcome = p.get('outcomeIndex') # 0 = YES, 1 = NO généralement
                outcome_label = "OUI" if outcome == 0 else "NON"
                
                cur_price = float(p.get('currentPrice', 0))
                avg_price = float(p.get('avgPrice', 0))
                
                # Calcul profit théorique
                pnl_pct = ((cur_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
                
                my_pos.append({
                    "Marché": title,
                    "Choix": outcome_label,
                    "Prix Achat": avg_price,
                    "Prix Actuel": cur_price,
                    "PnL": pnl_pct
                })
            
            df_pos = pd.DataFrame(my_pos)
            
            if not df_pos.empty:
                st.dataframe(
                    df_pos,
                    column_config={
                        "Prix Achat": st.column_config.NumberColumn(format="%.2f"),
                        "Prix Actuel": st.column_config.NumberColumn(format="%.2f"),
                        "PnL": st.column_config.NumberColumn("Profit %", format="%.1f%%")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Aucune position active trouvée sur ce compte.")
        else:
            st.info("Impossible de charger les positions ou portefeuille vide.")