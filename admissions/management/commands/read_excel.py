import os
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Advanced data analyzer: Reads ALL sheets with formatting, validation, and stats.'

    def handle(self, *args, **kwargs):
        file_path = os.path.join(settings.BASE_DIR, 'static', 'data', 'courses.xlsx')
        
        try:
            # 1. Read ALL sheets with specific data type handling
            all_sheets = pd.read_excel(file_path, sheet_name=None, dtype=str)
            
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(self.style.SUCCESS(f"  📁 INFINITY ACADEMY - ADVANCED EXCEL ANALYZER"))
            self.stdout.write("=" * 80)
            self.stdout.write(f"  ✅ File: {file_path}")
            self.stdout.write(f"  📊 Sheets Found: {len(all_sheets)}")
            self.stdout.write("=" * 80 + "\n")

            # 2. Process each sheet
            for sheet_name, df in all_sheets.items():
                self.stdout.write(self.style.HTTP_INFO(f"  📄 ANALYZING SHEET: '{sheet_name}'"))
                self.stdout.write(f"     Rows: {len(df)}, Columns: {len(df.columns)}")
                
                # 3. Data Quality Check: Detect invisible spaces in column headers
                dirty_cols = [col for col in df.columns if col != col.strip()]
                if dirty_cols:
                    self.stdout.write(self.style.ERROR(f"     ⚠️  WARNING: Hidden spaces detected in columns: {dirty_cols}"))
                    self.stdout.write(self.style.ERROR("     ℹ️  Hint: This will break database imports. Clean the header in Excel."))
                
                # 4. Advanced Statistics
                self.stdout.write(f"     ℹ️  Data Types: {dict(df.dtypes)}")
                
                # Count empty cells
                empty_cells = df.isnull().sum().sum()
                if empty_cells > 0:
                    self.stdout.write(f"     ⚠️  Empty/Null values detected across {empty_cells} cells.")
                
                # Show unique counts for first 2 categorical columns
                for i, col in enumerate(df.columns):
                    if i < 2:  # Check first 2 columns
                        unique_vals = df[col].nunique()
                        if unique_vals > 1:
                            self.stdout.write(f"     🏷️  Unique '{col}' values: {df[col].dropna().unique().tolist()}")
                
                self.stdout.write("-" * 40)
                self.stdout.write("     📋 PREVIEW OF DATA (First 10 rows):")
                
                # 5. Custom Pretty Printer (No external libraries needed)
                self._print_pretty_table(df, num_rows=10)
                
                self.stdout.write("\n" + "=" * 80 + "\n")

            self.stdout.write(self.style.SUCCESS("  ✅ Analysis Complete. Verify the preview before importing!"))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'❌ File not found at: {file_path}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ An unexpected error occurred: {e}'))

    # ---------------------------------------------------------
    # 🔥 ADVANCED FORMATTING: Draws a perfect ASCII table
    # ---------------------------------------------------------
    def _print_pretty_table(self, df, num_rows=5):
        if df.empty:
            self.stdout.write("     [Empty Sheet]")
            return

        # Get the first X rows
        preview = df.head(num_rows)
        
        # Calculate optimal column widths (capped at 45 chars to keep terminal readable)
        widths = {}
        for col in preview.columns:
            max_width = len(str(col))
            for val in preview[col]:
                max_width = max(max_width, len(str(val)))
            widths[col] = min(max_width + 2, 45)  # Add padding, cap at 45
        
        # 1. Create the Header
        header = "| " + " | ".join([f"{col:<{widths[col]}}" for col in preview.columns]) + " |"
        self.stdout.write("     " + header)
        self.stdout.write("     " + "-" * len(header))
        
        # 2. Create the Data Rows
        for _, row in preview.iterrows():
            row_str = "| " + " | ".join([f"{str(row[col]):<{widths[col]}}" for col in preview.columns]) + " |"
            self.stdout.write("     " + row_str)