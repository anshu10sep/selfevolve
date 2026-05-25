"""
Skill to generate a frontend dashboard widget for displaying the top 20 selected stocks.
Supports both Streamlit rendering and raw HTML generation for flexible integration into the SelfEvolve system.
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)

try:
    import streamlit as st
except ImportError:
    st = None

def render_streamlit_top_stocks(top_stocks_data: list):
    """
    Renders a Streamlit widget to display the top 20 stocks list with basic metrics.
    
    Args:
        top_stocks_data (list): A list of dictionaries containing stock data.
                                Expected keys: 'symbol', 'price', 'volume', 'change_pct', etc.
    """
    if not st:
        logger.error("Streamlit is not installed. Cannot render Streamlit widget.")
        return
        
    st.subheader("🎯 Top 20 Selected Stocks for Trading")
    
    if not top_stocks_data:
        st.info("No top stocks data available at the moment.")
        return
        
    # Convert to DataFrame for easier display
    df = pd.DataFrame(top_stocks_data)
    
    # Ensure we only display the top 20
    df = df.head(20)
    
    # Display top 3 as metric cards for quick insights
    st.markdown("### Top 3 Highlights")
    cols = st.columns(3)
    for i, col in enumerate(cols):
        if i < len(df):
            row = df.iloc[i]
            symbol = row.get('symbol', f'Stock {i+1}')
            price = row.get('price', 0.0)
            change = row.get('change_pct', 0.0)
            
            # Handle missing or non-numeric data gracefully
            try:
                price_val = float(price)
                price_str = f"${price_val:.2f}"
            except (ValueError, TypeError):
                price_str = str(price)
                
            try:
                change_val = float(change)
                change_str = f"{change_val:.2f}%"
            except (ValueError, TypeError):
                change_str = str(change)
            
            col.metric(
                label=symbol,
                value=price_str,
                delta=change_str
            )
            
    st.markdown("### Full Top 20 List")
    
    # Format the dataframe for the table
    display_df = df.copy()
    
    if 'symbol' in display_df.columns:
        display_df = display_df.set_index('symbol')
        
    if 'price' in display_df.columns:
        display_df['price'] = display_df['price'].apply(
            lambda x: f"${float(x):.2f}" if pd.notnull(x) and isinstance(x, (int, float, str)) and str(x).replace('.','',1).isdigit() else x
        )
        
    if 'change_pct' in display_df.columns:
        display_df['change_pct'] = display_df['change_pct'].apply(
            lambda x: f"{float(x):.2f}%" if pd.notnull(x) and isinstance(x, (int, float, str)) and str(x).replace('.','',1).replace('-','',1).isdigit() else x
        )
        
    if 'volume' in display_df.columns:
        display_df['volume'] = display_df['volume'].apply(
            lambda x: f"{int(float(x)):,}" if pd.notnull(x) and isinstance(x, (int, float, str)) and str(x).replace('.','',1).isdigit() else x
        )
        
    # Display metrics as an interactive table
    st.dataframe(display_df, use_container_width=True)


def generate_html_top_stocks(top_stocks_data: list) -> str:
    """
    Generates an HTML widget to display the top 20 stocks list with basic metrics.
    Useful for web dashboards not using Streamlit.
    
    Args:
        top_stocks_data (list): A list of dictionaries containing stock data.
                                
    Returns:
        str: HTML string representing the widget.
    """
    if not top_stocks_data:
        return "<div class='widget'><h3>🎯 Top 20 Selected Stocks for Trading</h3><p>No data available.</p></div>"
        
    df = pd.DataFrame(top_stocks_data).head(20)
    
    html = "<div class='top-stocks-widget' style='font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>"
    html += "<h3 style='margin-top: 0; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;'>🎯 Top 20 Selected Stocks for Trading</h3>"
    
    # Generate a summary of top 3
    html += "<div style='display: flex; gap: 15px; margin-bottom: 25px;'>"
    for i, row in df.head(3).iterrows():
        symbol = row.get('symbol', 'N/A')
        price = row.get('price', 0.0)
        change = row.get('change_pct', 0.0)
        
        try:
            change_val = float(change)
            color = "#27ae60" if change_val >= 0 else "#c0392b"
            change_str = f"{change_val:.2f}%"
        except (ValueError, TypeError):
            color = "#7f8c8d"
            change_str = str(change)
            
        try:
            price_str = f"${float(price):.2f}"
        except (ValueError, TypeError):
            price_str = str(price)
        
        html += f"""
        <div style='flex: 1; padding: 15px; background: #f8f9fa; border-radius: 8px; text-align: center; border: 1px solid #ecf0f1;'>
            <strong style='font-size: 1.4em; color: #2c3e50;'>{symbol}</strong><br/>
            <span style='font-size: 1.2em; color: #34495e;'>{price_str}</span><br/>
            <span style='color: {color}; font-weight: bold; font-size: 1.1em;'>{change_str}</span>
        </div>
        """
    html += "</div>"
    
    # Generate the table
    html += "<table style='width: 100%; border-collapse: collapse; font-size: 0.95em;'>"
    html += "<thead><tr style='background-color: #f1f2f6; color: #2c3e50;'>"
    
    columns = [col for col in df.columns if col != 'symbol']
    html += "<th style='padding: 12px 8px; text-align: left; border-bottom: 2px solid #bdc3c7;'>Symbol</th>"
    for col in columns:
        header_name = str(col).replace('_', ' ').title()
        html += f"<th style='padding: 12px 8px; text-align: left; border-bottom: 2px solid #bdc3c7;'>{header_name}</th>"
    html += "</tr></thead><tbody>"
    
    for idx, row in df.iterrows():
        bg_color = "#ffffff" if idx % 2 == 0 else "#f9f9f9"
        html += f"<tr style='background-color: {bg_color};'>"
        html += f"<td style='padding: 10px 8px; border-bottom: 1px solid #ecf0f1; color: #2980b9;'><strong>{row.get('symbol', '')}</strong></td>"
        
        for col in columns:
            val = row.get(col, '')
            if col == 'price':
                try:
                    val = f"${float(val):.2f}"
                except:
                    pass
            elif col == 'change_pct':
                try:
                    val_float = float(val)
                    color = "green" if val_float >= 0 else "red"
                    val = f"<span style='color: {color};'>{val_float:.2f}%</span>"
                except:
                    pass
            elif col == 'volume':
                try:
                    val = f"{int(float(val)):,}"
                except:
                    pass
            html += f"<td style='padding: 10px 8px; border-bottom: 1px solid #ecf0f1;'>{val}</td>"
        html += "</tr>"
        
    html += "</tbody></table></div>"
    return html

def get_dashboard_widget(top_stocks_data: list, format_type: str = 'streamlit'):
    """
    Main entry point to get the dashboard widget in the desired format.
    
    Args:
        top_stocks_data (list): List of stock data dictionaries.
        format_type (str): 'html' or 'streamlit'
        
    Returns:
        str or None: HTML string if format_type is 'html', None if 'streamlit' (renders directly).
    """
    if format_type.lower() == 'streamlit':
        return render_streamlit_top_stocks(top_stocks_data)
    else:
        return generate_html_top_stocks(top_stocks_data)