import streamlit as st
import pandas as pd
from pathlib import Path
from io import StringIO
import traceback
import re

# Set page configuration
st.set_page_config(
    page_title="Product Progress Tracker",
    layout="wide"
)

# Database file path
DB_FILE = "database.csv"


# Initialize the database if it doesn't exist
def init_db():
    if not Path(DB_FILE).exists():
        df = pd.DataFrame(columns=["Sub-productNumber", "progress"])
        df.to_csv(DB_FILE, index=False)


# Convert percentage strings to float (e.g., "4%" → 4.0)
def convert_percentage(progress):
    if isinstance(progress, str):
        # Remove % sign and convert to float
        match = re.match(r"^(\d+\.?\d*)%?$", progress.strip())
        if match:
            return float(match.group(1))
    elif pd.isna(progress):
        return 0.0
    return float(progress)


# Load the database and ensure progress is numeric
def load_db():
    try:
        db = pd.read_csv(DB_FILE)
        # Convert progress to numeric percentages
        db['progress'] = db['progress'].apply(convert_percentage)
        return db
    except Exception as e:
        st.error(f"Error loading database: {str(e)}")
        return pd.DataFrame(columns=["Sub-productNumber", "progress"])


# Save to database
def save_db(df):
    try:
        df.to_csv(DB_FILE, index=False)
    except Exception as e:
        st.error(f"Error saving database: {str(e)}")
        raise


# Convert DataFrame to CSV for download
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')


# Style DataFrame to highlight new entries with progress > 4%
def highlight_rows(row):
    if row['is_new'] and row['progress'] > 4:
        return ['background-color: #90EE90'] * len(row)  # Light green
    elif row['is_new']:
        return ['background-color: #FFFF99'] * len(row)  # Light yellow
    else:
        return [''] * len(row)


# Process uploaded file and ensure progress is numeric
def process_upload(uploaded_file):
    try:
        if uploaded_file is None:
            return None

        # Read the uploaded file while preserving all columns
        try:
            new_data = pd.read_csv(uploaded_file)
        except UnicodeDecodeError:
            uploaded_file.seek(0)  # Reset file pointer
            new_data = pd.read_csv(uploaded_file, encoding='latin-1')

        # Check for required columns
        required_columns = ["Sub-productNumber", "progress"]
        missing_columns = [col for col in required_columns if col not in new_data.columns]

        if missing_columns:
            st.error(f"Missing required columns: {', '.join(missing_columns)}")
            return None

        # Convert progress to numeric percentages
        new_data['progress'] = new_data['progress'].apply(convert_percentage)

        # Check for invalid progress values
        invalid_mask = new_data['progress'].isna() | (new_data['progress'] < 0) | (new_data['progress'] > 100)
        if invalid_mask.any():
            invalid_rows = new_data[invalid_mask]
            st.warning(
                f"Warning: Found {len(invalid_rows)} rows with invalid progress values (should be 0-100%). These will be treated as 0%.")
            st.dataframe(invalid_rows)
            # Set invalid values to 0
            new_data.loc[invalid_mask, 'progress'] = 0

        return new_data
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        st.text(traceback.format_exc())
        return None


# Main app
def main():
    st.title("📊 Product Progress Tracker")
    st.write("Upload a CSV file to update the product progress database")

    # Initialize database
    init_db()
    db = load_db()
    if 'is_new' not in db.columns:
        db['is_new'] = False

    # Show current database
    with st.expander("📂 Current Database", expanded=False):
        if db.empty:
            st.info("Database is currently empty")
        else:
            # Apply highlighting before display
            st.dataframe(db.style.apply(highlight_rows, axis=1))

            st.download_button(
                label="⬇️ Download Current Database",
                data=convert_df_to_csv(db.drop(columns=['is_new'])),
                file_name="current_product_database.csv",
                mime="text/csv",
                key='download_current'
            )

    # File upload section
    st.markdown("---")
    st.subheader("📤 Upload New Data")

    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type="csv",
        help="Upload a CSV file with 'Sub-productNumber' and 'progress' columns (percentage values like '4%' or '5.5%')"
    )

    if uploaded_file is not None:
        new_data = process_upload(uploaded_file)

        if new_data is not None:
            st.success("✅ File uploaded and validated successfully!")

            with st.expander("👀 Preview Uploaded Data", expanded=True):
                st.write("Progress values have been converted to numbers (e.g., '4%' → 4.0)")
                st.dataframe(new_data.head())
                st.write(f"**Records to process:** {len(new_data):,}")
                st.write(f"**Unique products:** {new_data['Sub-productNumber'].nunique():,}")

            if st.button("🚀 Process Data", type="primary"):
                # Initialize results
                results = {
                    'new_products': 0,
                    'updated_records': 0,
                    'warnings': 0,
                    'warning_messages': []
                }

                # Process each row in the uploaded data
                for _, row in new_data.iterrows():
                    product_num = row["Sub-productNumber"]
                    new_progress = row["progress"]
                    existing_index = db.index[db["Sub-productNumber"] == product_num]

                    if len(existing_index) == 0:
                        # New product - add to database
                        new_row = row.to_dict()
                        new_row['is_new'] = True
                        db = pd.concat([db, pd.DataFrame([new_row])], ignore_index=True)
                        results['new_products'] += 1
                    else:
                        # Existing product - check progress
                        old_progress = db.loc[existing_index[0], "progress"]

                        if new_progress > old_progress:
                            # Update all columns for existing record
                            db.loc[existing_index[0], row.index] = row
                            db.loc[existing_index[0], 'is_new'] = False  # Not new anymore
                            results['updated_records'] += 1
                        else:
                            warning_msg = f"⚠️ Product {product_num} has progress {new_progress}% (not greater than existing {old_progress}%)"
                            results['warning_messages'].append(warning_msg)
                            results['warnings'] += 1

                # Save the updated database
                try:
                    save_db(db.drop(columns=['is_new']))  # Save without the temporary column

                    # Show summary
                    st.success("🎉 Processing complete!")

                    col1, col2, col3 = st.columns(3)
                    col1.metric("New Products", results['new_products'])
                    col2.metric("Updated Records", results['updated_records'])
                    col3.metric("Warnings", results['warnings'])

                    # Show warnings if any
                    if results['warning_messages']:
                        with st.expander("⚠️ Warning Details", expanded=False):
                            for msg in results['warning_messages']:
                                st.warning(msg)

                    # Show updated database with highlighting
                    st.subheader("🔄 Updated Database")

                    # Show highlighted entries first
                    highlighted = db[db['is_new'] & (db['progress'] > 4)]
                    if not highlighted.empty:
                        st.subheader("🌟 Highlighted New Entries (progress > 4%)")
                        st.dataframe(highlighted.style.apply(highlight_rows, axis=1))

                    # Show full database
                    st.dataframe(db.style.apply(highlight_rows, axis=1))

                    # Download button
                    st.download_button(
                        label="⬇️ Download Updated Database",
                        data=convert_df_to_csv(db.drop(columns=['is_new'])),
                        file_name="updated_product_database.csv",
                        mime="text/csv",
                        key='download_updated'
                    )

                except Exception as e:
                    st.error(f"❌ Failed to save database: {str(e)}")
                    st.text(traceback.format_exc())


if __name__ == "__main__":
    main()