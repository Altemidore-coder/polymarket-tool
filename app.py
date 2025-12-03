
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
        /* Style des métriques */
        div[data-testid="stMetricValue"] { font-size: 1.2rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Master")

# --- CONSTANTES ---
MAIN_CATEGORIES = ["Politics", "Crypto", "Sports", "Business", "Science", "Pop Culture", "News"]

# --- FONCTIONS API ---

@st.cache_data(ttl=60)
def fetch_active_markets(limit=1000):
    """Récupère les 1000 marchés les plus urgents/actifs pour l'Explorer et le Mapping de prix"""
    url = "https://gamma-api.polymarket.com/events"
    params = {
        "limit": limit, 
        "active": "true", 
        "closed": "false", 
        "order": "volume", # On prend par volume pour avoir les prix les plus fiables
        "ascending": "false"
    }
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except: return []

def fetch_user_positions(address):
    """Récupère le portfolio via l'API Data"""
    if len(address) < 10: return []
    url = "https://data-api.polymarket.com/positions"
    params = {"user": address, "sizeThreshold": "0.1", "limit": "100"}
    try:
        r = requests.get(url, params=params)
        return r.json()
    except: return []

# --- CHARGEMENT DES DONNÉES ---
raw_data = fetch_active_markets()

# --- CONSTRUCTION DU MAPPING DE PRIX (La Clé du succès) ---
# On crée un dictionnaire : { "slug-du-marché": [PrixYes, PrixNo] }
price_oracle = {}
if raw_data:
    for item in raw_data:
        slug = item.get('slug') # ex: will-trump-win
        if not slug or not item.get('markets'): continue
        try:
            # On récupère les prix du marché principal
            prices = json.loads(item['markets'][0].get('outcomePrices', '["0","0"]'))
            price_oracle[slug] = prices # Stocke ["0.65", "0.35"]
        except: pass

# --- UI: BARRE DE RÉGLAGES (ACCORDÉON) ---
with st.expander("⚙️ RÉGLAGES & COMPTE (Cliquer pour ouvrir)", expanded=False):
    
    st.subheader("👤 Mon Compte")
    # Astuce : on met une valeur par défaut vide pour éviter l'erreur si vide
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

# ==========================================
# ONGLET 1 : EXPLORATEUR (RESTAURÉ)
# ==========================================
with tab1:
    explorer_list = []
    if raw_data:
        for item in raw_data:
            if not item.get('markets'): continue
            
            # 1. Filtres
            title = item.get('title', '').lower()
            if exclude_bots and ("up or down" in title or "up/down" in title or "15min" in title): continue
            
            # Catégorie
            tags = [t.get('label') for t in item.get('tags', []) if t.get('label')]
            cat = "Autre"
            for m_cat in MAIN_CATEGORIES:
                if m_cat in tags:
                    cat = m_cat
                    break
            if not cat in MAIN_CATEGORIES and tags: cat = tags[0]
            if cat not in selected_cats: continue

            # 2. Temps & Metrics
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
            
            # Prix via Oracle interne (plus fiable) ou raw
            slug = item.get('slug')
            prices = price_oracle.get(slug, ["0", "0"])
            p_yes = float(prices[0])

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
        else: st.info("Aucun marché trouvé avec ces filtres.")

# ==========================================
# ONGLET 2 : PORTFOLIO (MAPPING SLUG)
# ==========================================
with tab2:
    if not user_address:
        st.warning("⚠️ Entre ton adresse dans 'Réglages' pour voir ton portfolio.")
    else:
        positions = fetch_user_positions(user_address)
        
        if positions:
            my_pos = []
            total_equity = 0
            
            for p in positions:
                size = float(p.get('size', 0))
                if size < 0.1: continue
                
                title = p.get('title', 'Inconnu')
                slug = p.get('marketSlug') # La clé de liaison !
                side_idx = int(p.get('outcomeIndex', 0))
                side_label = "OUI" if side_idx == 0 else "NON"
                avg_price = float(p.get('avgPrice', 0))
                
                # --- LOGIQUE DE PRIX ---
                current_price = 0
                source = "API"
                
                # 1. On cherche dans notre oracle (Données fraîches de l'Explorer)
                if slug in price_oracle:
                    try:
                        current_price = float(price_oracle[slug][side_idx])
                        source = "Live"
                    except: pass
                
                # 2. Si pas trouvé (ex: vieux marché pas dans le top 1000), fallback API
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
                    "Src": source # Debug pour savoir d'où vient le prix
                })
            
            df_pos = pd.DataFrame(my_pos)
            
            if not df_pos.empty:
                st.metric("Valeur Totale", f"${total_equity:,.2f}")
                
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
                        "Src": st.column_config.TextColumn("Source", help="Live = Prix frais, Old = Prix API")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else: st.info("Aucune position active.")
        else: st.error("Impossible de récupérer les positions. Vérifie l'adresse.")