#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import random as ra # Renamed random to ra for consistency with other scripts
import csv
import sys
import xml.etree.ElementTree as ET
import calendar # For hetu generation

try:
    from libs.kirjasto import gen_id, gen_timestamp
except ImportError:
    print('Error: libs.kirjasto.py missing or incomplete. Please ensure it is in the libs directory.')
    sys.exit(1)

# Color definitions (optional, for consistency)
if os.name == 'posix':
    red = '\u001b[31m'
    green = '\u001b[32m'
    yellow = '\u001b[33m'
    cyan = '\u001b[36m'
    reset = '\u001b[0m'
    bold = '\u001b[1m]'
else:
    red = green = yellow = cyan = reset = bold = ''


class ContractGenerator:
    """
    Generates contract XML files based on data from kp.csv and XML templates.
    """

    def __init__(self, kp_csv_path="kp.csv",
                 template_path="libs/sopimus_template.xml",
                 output_dir="xml/"):
        """
        Initializes the ContractGenerator.

        Args:
            kp_csv_path (str): Path to the input CSV file containing accounting point data.
            template_path (str): Path to the XML template for contracts.
            output_dir (str): Directory where generated XML files will be saved.
        """
        self.kp_csv_path = kp_csv_path
        self.xml_template_path = template_path
        self.xml_output_dir = output_dir

        self.name_files = {
            'mies': 'libs/mies.txt',      # Finnish male first names
            'nainen': 'libs/nainen.txt',  # Finnish female first names
            'sukunimet': 'libs/sukunimet.txt' # Finnish last names
        }
        self.loaded_names = {'mies': [], 'nainen': [], 'sukunimet': []}

        self._ensure_output_dir_exists()
        self._load_name_lists()

    def _ensure_output_dir_exists(self):
        """Ensures the XML output directory exists."""
        try:
            os.makedirs(self.xml_output_dir, exist_ok=True)
        except OSError as e:
            print(f"{red}Error creating output directory {self.xml_output_dir}: {e}{reset}")
            # Depending on desired behavior, could raise this error
            # For now, script will likely fail later if dir cannot be written to.

    def _load_name_lists(self):
        """Loads first and last names from text files."""
        for category, filepath in self.name_files.items():
            try:
                with open(filepath, 'r', encoding='latin-1') as f: # Original used latin-1
                    self.loaded_names[category] = [line.strip() for line in f if line.strip()]
                if not self.loaded_names[category]:
                    print(f"{yellow}Warning: Name list file {filepath} is empty.{reset}")
            except FileNotFoundError:
                print(f"{yellow}Warning: Name list file {filepath} not found. {category.capitalize()} names will be unavailable.{reset}")
            except IOError as e:
                print(f"{yellow}Warning: Could not read name list file {filepath}: {e}{reset}")

    def _generate_hetu(self, start_year=1900, end_year=1999):
        """
        Generates a random Finnish social security number (HETU).
        Original logic from sopimusgen.py.
        """
        CHECK_KEYS = "0123456789ABCDEFHJKLMNPRSTUVWXY"
        CENTURIES = {'18': '+', '19': '-', '20': 'A'} # Add more if needed for broader year ranges

        year = ra.randint(start_year, end_year)
        month = ra.randint(1, 12)
        day = ra.randint(1, calendar.monthrange(year, month)[1])

        year_str = str(year)
        century_code = year_str[0:2]
        century_sep = CENTURIES.get(century_code, 'A') # Default to 'A' if century not in map

        # Individual number part (originally 900-999 for test range, can be 002-899 for real)
        # For broader unique HETUs, this range should be wider.
        order_num = ra.randint(2, 899) # More realistic range

        # Format: DDMMYYCIIIT (Day, Month, Year (last two digits), Century Separator, Individual number (3 digits), Checksum char)
        hetu_base_num_str = f"{day:02d}{month:02d}{year_str[2:4]}{order_num:03d}"

        try:
            check_number_val = int(hetu_base_num_str)
            checksum_char = CHECK_KEYS[check_number_val % 31]
        except ValueError: # Should not happen if logic is correct
            print(f"{red}Error generating HETU checksum, numeric part invalid: {hetu_base_num_str}{reset}")
            return "ERRORHETU0X" # Placeholder for error

        return f"{day:02d}{month:02d}{year_str[2:4]}{century_sep}{order_num:03d}{checksum_char}"

    def _generate_henkilo(self):
        """
        Generates a random Finnish person's name.
        Original logic from sopimusgen.py.
        """
        try:
            if ra.randint(0, 1): # 50/50 chance for male/female first name
                if self.loaded_names['mies']:
                    etunimi = ra.choice(self.loaded_names['mies'])
                else: # Fallback if male names not loaded
                    etunimi = "Matti"
            else:
                if self.loaded_names['nainen']:
                    etunimi = ra.choice(self.loaded_names['nainen'])
                else: # Fallback if female names not loaded
                    etunimi = "Maija"

            if self.loaded_names['sukunimet']:
                sukunimi = ra.choice(self.loaded_names['sukunimet'])
            else: # Fallback if last names not loaded
                sukunimi = "Meikäläinen"

            return f"{etunimi} {sukunimi}"
        except Exception as e: # Catch any unexpected errors during name generation
            print(f"{yellow}Warning: Error generating person name: {e}. Using default.{reset}")
            return "Nimi Puuttuu Testihenkilö"


    def _produce_single_xml(self, contract_data: dict):
        """
        Produces a single contract XML file based on the provided data.
        """
        try:
            tree = ET.parse(self.xml_template_path)
        except FileNotFoundError:
            print(f"{red}Error: XML template file '{self.xml_template_path}' not found.{reset}")
            return False
        except ET.ParseError as e:
            print(f"{red}Error: Failed to parse XML template '{self.xml_template_path}': {e}{reset}")
            return False

        # Namespaces used in sopimus_template.xml (verify these from the template)
        # Original script used .// prefix which means find anywhere.
        # It's better to register namespaces if they are used consistently, or use full URI in find.
        # For now, replicating the .// approach with full URIs.
        ns_hdr = "urn:fi:Datahub:mif:common:HDR_Header:elements:v1"
        ns_f04 = "urn:fi:Datahub:mif:masterdata:F04_MasterDataContractEvent:elements:v1"
        # ns_f04_root = "urn:fi:Datahub:mif:masterdata:F04_MasterDataContractEvent:v1" # If needed for root element

        try:
            # Helper to find and set text, creates element if not found (simplified)
            def find_and_set(path_parts_with_ns, text_value):
                curr = tree.getroot()
                for ns_uri, tag_name in path_parts_with_ns:
                    found_el = curr.find(f".//{{{ns_uri}}}{tag_name}")
                    if found_el is None : # Simplified: doesn't create, just warns
                        print(f"{yellow}Warning: XML element path not fully found: .../{tag_name} in template.{reset}")
                        return
                    curr = found_el
                curr.text = str(text_value) if text_value is not None else ""

            # Fill XML based on contract_data and generated values
            # Header
            find_and_set([(ns_hdr, "Identification")], gen_id(True)) # Assuming this gen_id is for message ID
            find_and_set([(ns_hdr, "PhysicalSenderEnergyParty"), (ns_hdr, "Identifier")], contract_data.get('ddq'))
            find_and_set([(ns_hdr, "JuridicalSenderEnergyParty"), (ns_hdr, "Identifier")], contract_data.get('ddq'))
            find_and_set([(ns_hdr, "Creation")], gen_timestamp())

            # Contract specific data (F04 elements)
            find_and_set([(ns_f04, "StartOfOccurrence")], gen_timestamp('True')) # Midnight of current day
            find_and_set([(ns_f04, "MeteringPointOfContract"), (ns_f04, "Identifier")], contract_data.get('ap'))
            find_and_set([(ns_f04, "MeteringGridAreaUsedDomainLocation"), (ns_f04, "Identifier")], contract_data.get('mga'))
            find_and_set([(ns_f04, "SupplierOfContract"), (ns_f04, "Identifier")], contract_data.get('ddq'))

            # MasterDataContract: Original had [1] index, assume it's second child or specific tag if unique
            # For ET, findall might be needed if there are multiple 'MasterDataContract' elements.
            # Assuming it's a unique 'ContractReference'.
            contract_ref_elem = tree.find(f".//{{{ns_f04}}}MasterDataContract/{{{ns_f04}}}ContractReference") # Example path
            if contract_ref_elem is not None:
                contract_ref_elem.text = str(ra.randint(1, 9999999999))
            else: # Fallback if specific path not found, try original less specific (might be error prone)
                mdc_elements = tree.findall(f".//{{{ns_f04}}}MasterDataContract")
                if mdc_elements and len(mdc_elements) > 0 : # If MasterDataContract itself is the target (unlikely) or a list
                     # This part is tricky without seeing template. Original used find(...)[1].text
                     # This often means the second child of the found element, not the second occurrence of the tag.
                     # For safety, let's assume it's ContractReference as above.
                     pass

            find_and_set([(ns_f04, "ConsumerInvolvedCustomerParty"), (ns_f04, "Identifier")], contract_data.get('hetu_val'))
            find_and_set([(ns_f04, "Name")], contract_data.get('henkilo_val')) # Name of the consumer

            output_file_path = os.path.join(self.xml_output_dir, f"sopimus_{contract_data['ap']}.xml")
            tree.write(output_file_path, encoding='utf-8', xml_declaration=True)
            print(f"Generated contract XML: {output_file_path}")
            return True
        except IOError as e:
            print(f"{red}Error writing XML file for AP {contract_data.get('ap', 'N/A')}: {e}{reset}")
        except Exception as e: # Catch other XML manipulation errors
            print(f"{red}Error producing XML for AP {contract_data.get('ap', 'N/A')}: {e}{reset}")
        return False

    def generate_contracts(self):
        """
        Reads accounting point data from kp.csv and generates contract XML files.
        """
        print(f"{cyan}Starting contract generation from {self.kp_csv_path}...{reset}")
        if not os.path.exists(self.kp_csv_path):
            print(f"{red}Error: Input CSV file '{self.kp_csv_path}' not found. Please run kpgen.py first.{reset}")
            return

        generated_count = 0
        failed_count = 0
        try:
            with open(self.kp_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                required_cols = ['Accounting point', 'Supplier', 'MGA']
                missing_cols = [col for col in required_cols if col not in reader.fieldnames]
                if missing_cols:
                    print(f"{red}Error: CSV file '{self.kp_csv_path}' is missing required columns: {', '.join(missing_cols)}{reset}")
                    return

                for row_num, row in enumerate(reader):
                    try:
                        ap_id = row['Accounting point']
                        ddq = row['Supplier'] # Assuming this is the DDQ/supplier ID
                        mga = row['MGA']

                        if not all([ap_id, ddq, mga]):
                            print(f"{yellow}Warning: Skipping row {row_num + 2} in {self.kp_csv_path} due to missing required data (AP, Supplier, or MGA).{reset}")
                            continue

                        hetu_val = self._generate_hetu()
                        henkilo_val = self._generate_henkilo()

                        current_contract_data = {
                            'ap': ap_id,
                            'ddq': ddq,
                            'mga': mga,
                            'hetu_val': hetu_val,
                            'henkilo_val': henkilo_val
                        }

                        Printer(f"Processing AP: {ap_id}...")
                        if self._produce_single_xml(current_contract_data):
                            generated_count +=1
                        else:
                            failed_count += 1

                    except KeyError as e:
                        print(f"{yellow}Warning: Skipping row {row_num + 2} in {self.kp_csv_path} due to missing column: {e}{reset}")
                        failed_count +=1
                        continue
                    except Exception as e_inner: # Catch unexpected errors per row
                        print(f"{red}Error processing row {row_num + 2} for AP {row.get('Accounting point', 'UNKNOWN')}: {e_inner}{reset}")
                        failed_count +=1

            sys.stdout.write("\n") # Ensure newline after Printer
            print(f"{cyan}Contract generation process finished.{reset}")
            if generated_count > 0: print(f"{green}Successfully generated {generated_count} contract XML files.{reset}")
            if failed_count > 0: print(f"{red}Failed to generate {failed_count} contract XML files.{reset}")
            if generated_count == 0 and failed_count == 0 : print(f"{yellow}No data processed from {self.kp_csv_path}. File might be empty or all rows had issues.{reset}")

        except FileNotFoundError: # Should be caught by initial os.path.exists, but as safeguard
             print(f"{red}Error: Input CSV file '{self.kp_csv_path}' disappeared during processing.{reset}")
        except Exception as e: # Catch other potential errors like CSV parsing issues at file level
            print(f"{red}Error reading or parsing {self.kp_csv_path}: {e}{reset}")


if __name__ == "__main__":
    print(f"{cyan}--- Contract Generator (sopimusgen.py) ---{reset}")
    try:
        generator = ContractGenerator()
        generator.generate_contracts()
    except FileNotFoundError as e: # e.g., if libs/template or name files are missing and constructor fails
        print(f"{red}{bold}Critical file error during initialization: {e}{reset}")
    except ImportError as e: # Should have been caught earlier, but as a final catch
        print(f"{red}{bold}Critical import error: {e}{reset}")
    except KeyboardInterrupt:
        print(f"\n{yellow}Program cancelled by user.{reset}")
    except Exception as e:
        import traceback
        print(f"{red}{bold}An unexpected critical error occurred:\n{e}\n{traceback.format_exc()}{reset}")
    finally:
        print(f"{cyan}--- sopimusgen.py finished ---{reset}")

```
