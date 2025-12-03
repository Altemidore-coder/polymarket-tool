
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Tracker", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDataFrame { font-size: 0.8rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Tracker (CLOB Edition)")

# --- FONCTIONS API ---

@st.cache_data(ttl=60)
def fetch_markets(limit=1000):
    """Récupère les infos générales des marchés (Titres, Images, Dates)"""
    url = "https://gamma-api.polymarket.com/events"
    params = {"limit": limit, "active": "true", "closed": "false", "order": "endDate", "ascending": "true"}
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except: return []

def fetch_user_positions(address):
    """Récupère tes positions (Quantités et Prix d'achat)"""
    if len(address) < 10: return []
    # On utilise l'API V2 Data qui est plus robuste
    url = f"https://data-api.polymarket.com/positions?user={address}"
    try:
        r = requests.get(url)
        return r.json()
    except: return []

def fetch_clob_prices():
    """
    LA SOLUTION ULTIME : Récupère les prix en direct du moteur de trading (CLOB).
    Renvoie un dictionnaire { "0xTokenID...": 0.65 }
    """
    url = "https://clob.polymarket.com/prices"
    try:
        r = requests.get(url)
        data = r.json()
        
        # On transforme la liste en dictionnaire pour une recherche instantanée
        # L'API renvoie souvent : [{"token_id": "...", "price": "..."}]
        price_map = {}
        for item in data:
            try:
                # Le prix retourné est souvent une string, on convertit
                p = float(item.get('price', 0))
                t_id = item.get('token_id')
                if t_id:
                    price_map[t_id] = p
            except: pass
            
        return price_map
    except Exception as e:
        print(f"Erreur CLOB: {e}")
        return {}

# --- INITIALISATION ---
raw_data = fetch_markets()

# --- BARRE DE RÉGLAGES ---
with st.expander("⚙️ RÉGLAGES & COMPTE", expanded=True):
    st.write("### 👤 Mon Compte")
    user_address = st.text_input("Adresse Polygon (0x...)", help="Ton adresse publique")
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        max_days = st.slider("Jours Max", 0, 30, 7)
    with c2:
        min_liquidity = st.number_input("Liq. Min ($)", value=100)

    # Bouton de debug pour vérifier si l'adresse fonctionne
    if st.button("🔄 Tout Actualiser"):
        st.cache_data.clear()
        st.rerun()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["🌎 MARCHÉS", "💼 PORTFOLIO"])

# --- ONGLET 1 : EXPLORATEUR (Simple) ---
with tab1:
    market_list = []
    if raw_data:
        for item in raw_data:
            if not item.get('markets'): continue
            m = item['markets'][0]
            
            # Filtres basiques pour aller vite
            end_date = item.get('endDate')
            hours_left = 9999
            if end_date:
                try:
                    dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    hours_left = (dt - datetime.now(dt.tzinfo)).total_seconds() / 3600
                except: pass
            
            if hours_left > (max_days * 24): continue
            
            try:
                prices = json.loads(m.get('outcomePrices', '["0","0"]'))
                price = float(prices[0])
            except: price = 0
            
            market_list.append({
                "Titre": item.get('title'),
                "Prix (Yes)": price,
                "Vol.": int(item.get('volume', 0)),
                "Lien": f"https://polymarket.com/event/{item.get('slug')}"
            })
            
    st.dataframe(pd.DataFrame(market_list), use_container_width=True, hide_index=True)

# --- ONGLET 2 : PORTFOLIO (CLOB) ---
with tab2:
    if not user_address:
        st.info("Entre ton adresse ci-dessus.")
    else:
        with st.spinner("Récupération des prix CLOB en direct..."):
            # 1. On charge tes positions
            my_positions = fetch_user_positions(user_address)
            
            # 2. On charge TOUS les prix du marché (La clé magique)
            clob_prices = fetch_clob_prices()
            
            if my_positions:
                clean_pos = []
                total_val = 0
                
                for p in my_positions:
                    size = float(p.get('size', 0))
                    if size < 0.1: continue # On ignore les poussières
                    
                    # L'ID unique de l'actif (C'est ça le lien avec le CLOB !)
                    asset_id = p.get('asset') 
                    
                    title = p.get('title', 'Inconnu')
                    side = "OUI" if p.get('outcomeIndex') == 0 else "NON"
                    avg_buy = float(p.get('avgPrice', 0))
                    
                    # 3. RECHERCHE DU PRIX
                    # On regarde si cet asset_id est dans notre liste de prix CLOB
                    current_price = clob_prices.get(asset_id, 0.0)
                    
                    # Fallback : Si le CLOB ne l'a pas (rare), on prend le prix estimé de l'API Position
                    if current_price == 0:
                        current_price = float(p.get('currentPrice', 0))

                    val = size * current_price
                    total_val += val
                    
                    pnl = 0
                    if avg_buy > 0:
                        pnl = ((current_price - avg_buy) / avg_buy) * 100
                    
                    clean_pos.append({
                        "Marché": title,
                        "Côté": side,
                        "Parts": size,
                        "Achat": avg_buy,
                        "Actuel": current_price,
                        "Valeur": val,
                        "PnL": pnl
                    })
                
                df = pd.DataFrame(clean_pos)
                if not df.empty:
                    st.metric("Valeur Totale", f"${total_val:,.2f}")
                    
                    # On colore le PnL en fonction du résultat
                    st.dataframe(
                        df,
                        column_config={
                            "Marché": st.column_config.TextColumn(width="medium"),
                            "Achat": st.column_config.NumberColumn(format="%.3f"),
                            "Actuel": st.column_config.NumberColumn(format="%.3f"), # Doit être > 0 maintenant !
                            "Valeur": st.column_config.NumberColumn(format="$%.2f"),
                            "PnL": st.column_config.NumberColumn("Profit %", format="%.2f%%")
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.warning("Aucune position active trouvée.")
            else:
                st.error("Impossible de lire le portfolio. Vérifie l'adresse.")