
import streamlit as st

st.set_page_config(layout="wide")

from selenium import webdriver
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from io import StringIO
import pandas as pd

BASE_URL_articles = "https://dpm.tn/controle-technique/amc/liste-des-articles"

def make_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=chrome_options)


@st.cache_data
def get_articles():
    driver = make_driver()
    wait = WebDriverWait(driver, 30)
    try:
        driver.get(BASE_URL_articles)
        driver.switch_to.frame(wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe"))))
        return driver.execute_script("""
            var select = document.querySelector('select[name="it_codite"]');
            return Array.from(select.options)
                .filter(o => o.value)
                .map(o => [o.value, o.text.trim()]);
        """)
    finally:
        driver.quit()

@st.cache_data
def get_all_articles_table():
    driver = make_driver()
    wait = WebDriverWait(driver, 30)
    all_data = []

    try:
        # Get all article codes first
        articles = get_articles()
        total = len(articles)

        driver.get(BASE_URL_articles)
        driver.switch_to.frame(wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe"))))

        progress = st.progress(0, text="Chargement des données...")

        for i, (code, label) in enumerate(articles):
            try:
                # Select the article
                Select(wait.until(EC.presence_of_element_located((By.NAME, "it_codite")))).select_by_value(code)
                wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit']"))).click()
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                if "Pas de produit" not in driver.page_source:
                    table = wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
                    df = pd.read_html(StringIO(table.get_attribute("outerHTML")), header=0)[0]
                    df.columns = ["N", "Date", "Produit", "Importateur", "Fournisseur", "Provenance", "N° Lot", "Fabrication", "Expiration", "Extra"]
                    df["article_code"] = code
                    df["article_label"] = label
                    all_data.append(df)

                # Go back for next iteration
                driver.back()
                driver.switch_to.frame(wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe"))))

            except Exception as e:
                print(f"Error for {label}: {e}")

            progress.progress((i + 1) / total, text=f"Chargement... {i+1}/{total} ({label})")

        progress.empty()

    finally:
        driver.quit()

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None

######## UI ########
df = pd.read_csv("ACM_data.csv", index_col=0)



def page_recherche_acm(df):
    st.markdown("""
        <h1 style='text-align: center; color: #87CEEB;'>Recherche ACM</h1>
        <p style='text-align: center; color: #B0E0E6;'>Bienvenue sur la page de recherche ACM.</p>
    """, unsafe_allow_html=True)

    
    # Rename "N" column to "Référence"
    if "N" in df.columns:
        df = df.rename(columns={"N": "Référence"})

    columns_to_filter = [
        "Produit", "Importateur", "Fournisseur", "Provenance", "N° Lot", "Fabrication", "Expiration", "article_code", "article_label"
    ]

    # Use session state to store filter selections
    def make_clear_callback(key):
        def clear():
            st.session_state[key] = "(Tous)"
        return clear

    # Keep the original dataframe for cascading filters
    df_original = df.copy()

    left_col, right_col = st.columns([1, 3], gap="large")

    with left_col:
        # Refresh data button
        if st.button("🔄 Rafraichir les données", key="refresh_data", use_container_width=True):
            with st.spinner("Chargement des données en cours..."):
                new_data = get_all_articles_table()
                if new_data is not None:
                    new_data.to_csv("ACM_data.csv")
                    st.cache_data.clear()  # Clear cache to force reload
                    st.success("Données mises à jour avec succès!")
                    st.rerun()
                else:
                    st.error("Erreur lors du chargement des données.")

        
        st.markdown("<p style='color: red; font-size: 18px; font-weight: bold;'>⏱️ Cela peut prendre aux alentours d'une heure</p>", unsafe_allow_html=True)
        st.markdown("---")
        
        st.markdown("<h3>Filtres</h3>", unsafe_allow_html=True)
        for idx, col in enumerate(columns_to_filter):
            # Build filtered dataframe based on ALL OTHER filters (excluding current)
            df_for_current = df_original.copy()
            for other_idx, other_col in enumerate(columns_to_filter):
                if other_idx != idx:  # Skip the current column
                    other_key = f"select_{other_col}_{other_idx}"
                    if other_key in st.session_state and st.session_state[other_key] != "(Tous)":
                        df_for_current = df_for_current[df_for_current[other_col] == st.session_state[other_key]]
            
            # Get unique values from this filtered dataframe
            unique_values = df_for_current[col].dropna().unique()
            options = ["(Tous)"] + sorted(unique_values)
            key_select = f"select_{col}_{idx}"
            key_clear = f"clear_{col}_{idx}"
            cols = st.columns([4, 1])
            if key_select not in st.session_state:
                st.session_state[key_select] = "(Tous)"
            
            # Ensure the current selection is still in the available options
            current_selection = st.session_state[key_select]
            if current_selection not in options:
                current_selection = "(Tous)"
                st.session_state[key_select] = "(Tous)"
            
            selected = cols[0].selectbox(
                f"Filtrer par {col}",
                options=options,
                index=options.index(current_selection),
                key=key_select,
                help=f"Commencez à taper pour filtrer les options de {col}"
            )
            cols[1].button("❌", key=key_clear, on_click=make_clear_callback(key_select))

    # Apply ALL filters to create the final dataframe for the table
    df_filtered = df_original.copy()
    for idx, col in enumerate(columns_to_filter):
        key_select = f"select_{col}_{idx}"
        if key_select in st.session_state and st.session_state[key_select] != "(Tous)":
            df_filtered = df_filtered[df_filtered[col] == st.session_state[key_select]]
    
    # Use the filtered dataframe for the table
    df = df_filtered

    with right_col:
        st.markdown(f"<div style='text-align:center; margin-top:20px;'><b>Résultats: {len(df)} lignes</b></div>", unsafe_allow_html=True)
        # Custom CSS for wider table and bigger font
        st.markdown(
            """
            <style>
            .stDataFrame [data-testid="stHorizontalBlock"] { max-width: 100vw !important; }
            .stDataFrame table { font-size: 20px !important; }
            .stDataFrame th { 
                font-size: 26px !important; 
                background-color: #2C3E50 !important; 
                color: white !important; 
                font-weight: bold !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        st.dataframe(df, use_container_width=True, hide_index=True, height=700)

# Entry point for Streamlit app
if __name__ == "__main__" or True:  # True allows running in Streamlit
    page_recherche_acm(df)