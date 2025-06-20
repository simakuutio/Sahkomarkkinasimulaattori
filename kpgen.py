#!/usr/bin/python3
# -*- coding: utf-8 -*-

import random as ra
import csv
import sys
import os
import getopt
import xml.etree.ElementTree as ET

try:
    from libs.kirjasto import gen_id, gen_timestamp, add_check_digit
except ImportError:
    print('Error: libs.kirjasto.py missing. Please ensure it is in the libs directory.')
    sys.exit(1)

# Config import will be attempted in _load_config
# from libs.fconfig import jakeluverkkoyhtio, MGA, dealers, id_range, limit

class AccountingPointGenerator:
    def __init__(self, cmd_args=None):
        self.cmd_args = cmd_args if cmd_args else {}
        self.config = {}
        self.selected_dso = None
        self.selected_mga = None
        self.ap_type_code = None # e.g., AG01
        self.remote_readable_code = None # e.g., 1
        self.metering_method_code = None # e.g., E13
        self.num_aps_to_generate = 0

        self.generated_ap_ids = []
        self.osoitteet_list = []
        self.current_address_details = {} # To store details from _get_random_address for CSV

        self._load_config()
        self._load_dependencies()

    def _load_config(self):
        """Loads configuration from libs.fconfig."""
        try:
            from libs.fconfig import jakeluverkkoyhtio, MGA, dealers, id_range, limit
            self.config['jakeluverkkoyhtio'] = jakeluverkkoyhtio
            self.config['MGA'] = MGA
            self.config['dealers'] = dealers
            self.config['id_range'] = id_range
            self.config['limit'] = limit
        except ImportError:
            print('Error: libs.fconfig.py missing or incomplete. Please ensure it is in the libs directory and properly configured.')
            raise # Re-raise to be caught by main exception handler

        if not self.config.get('dealers'):
            print("Configuration Error: No dealers configured in libs/fconfig.py. Please check the 'dealers' list.")
            raise ValueError("Missing 'dealers' configuration in fconfig.py")

        if not self.config.get('jakeluverkkoyhtio'):
            print("Configuration Error: No 'jakeluverkkoyhtio' (DSOs) configured in libs/fconfig.py.")
            raise ValueError("Missing 'jakeluverkkoyhtio' configuration in fconfig.py")

        if not self.config.get('MGA'):
            print("Configuration Error: No 'MGA' (Metering Grid Areas) configured in libs/fconfig.py.")
            raise ValueError("Missing 'MGA' configuration in fconfig.py")

    def _load_dependencies(self):
        """Loads external dependencies like osoitteet.txt."""
        try:
            # Assuming osoitteet.txt is in libs directory, relative to where script is run or add specific path logic
            with open('libs/osoitteet.txt', 'r', encoding='latin-1') as f:
                self.osoitteet_list = [line.strip() for line in f if line.strip()]
            if not self.osoitteet_list:
                print("Error: 'libs/osoitteet.txt' is empty.")
                raise FileNotFoundError("libs/osoitteet.txt is empty.")
        except FileNotFoundError:
            print("Error: Dependency file 'libs/osoitteet.txt' not found.")
            raise # Re-raise to be caught by main exception handler
        except Exception as e:
            print(f"Error loading 'libs/osoitteet.txt': {e}")
            raise

    def _get_user_selection(self, items: list, prompt_message: str, item_names_key=None):
        """
        Generic helper for interactive selection from a list of items.
        item_names_key: Optional lambda to extract display names if items are complex.
        """
        if not items:
            print(f"Error: No items available for selection for: {prompt_message}")
            raise ValueError(f"No items for {prompt_message}")

        for i, item in enumerate(items):
            display_name = item if item_names_key is None else item_names_key(item)
            print(f"{i+1} - {display_name}")

        while True:
            try:
                ans = input(f"{prompt_message} (1-{len(items)}): ")
                ans_int = int(ans)
                if 1 <= ans_int <= len(items):
                    return items[ans_int-1]
                else:
                    print(f"Please select a number between 1 and {len(items)}.")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (SyntaxError, NameError): # Should not happen with input() then int()
                print("Invalid input format.")


    def _prompt_for_dso(self):
        """Prompts user to select a DSO."""
        print("Select DSO:")
        self.selected_dso = self._get_user_selection(self.config['jakeluverkkoyhtio'], "DSO")

    def _prompt_for_mga(self):
        """Prompts user to select an MGA."""
        print("Select MGA:")
        self.selected_mga = self._get_user_selection(self.config['MGA'], "MGA")

    def _prompt_for_ap_type(self):
        """Prompts user to select an Accounting Point type."""
        types = [('Non-production', 'AG01'), ('Production', 'AG02')]
        print("Select Accounting Point type:")
        selected_type_tuple = self._get_user_selection(types, "AP Type", item_names_key=lambda x: x[0])
        self.ap_type_code = selected_type_tuple[1]

    def _prompt_for_remote_readable(self):
        """Prompts user to select if AP is remote readable."""
        readable_options = [('Readable', '1'), ('Non-readable', '0')]
        print("Select Accounting Point mode (remote readable):")
        selected_readable_tuple = self._get_user_selection(readable_options, "Mode", item_names_key=lambda x: x[0])
        self.remote_readable_code = selected_readable_tuple[1]

    def _prompt_for_metering_method(self):
        """Prompts user to select the metering method."""
        methods = [('Continuous metering', 'E13'), ('Reading metering', 'E14'), ('Unmetered', 'E16')]
        print("Select Accounting Point metering method:")
        selected_method_tuple = self._get_user_selection(methods, "Metering Method", item_names_key=lambda x: x[0])
        self.metering_method_code = selected_method_tuple[1]

    def _prompt_for_num_aps(self):
        """Prompts user for the number of APs to generate."""
        limit = self.config.get('limit', 1000) # Default limit if not in config
        while True:
            try:
                ans = input(f"Amount of accounting points (1-{limit}): ")
                num = int(ans)
                if 1 <= num <= limit:
                    self.num_aps_to_generate = num
                    return
                else:
                    print(f"Value should be between 1 and {limit}.")
            except ValueError:
                print("Invalid input. Please enter a number.")

    def _determine_generation_parameters(self):
        """Determines all generation parameters from cmd args or prompts."""
        # DSO
        if 'jvy' in self.cmd_args and self.cmd_args['jvy'] in self.config['jakeluverkkoyhtio']:
            self.selected_dso = self.cmd_args['jvy']
        elif 'jvy' in self.cmd_args: # Provided but invalid
             raise ValueError(f"Provided DSO (jvy) '{self.cmd_args['jvy']}' is not in configured jakeluverkkoyhtio list.")
        else:
            self._prompt_for_dso()

        # MGA
        if 'mga' in self.cmd_args and self.cmd_args['mga'] in self.config['MGA']:
            self.selected_mga = self.cmd_args['mga']
        elif 'mga' in self.cmd_args:
            raise ValueError(f"Provided MGA '{self.cmd_args['mga']}' is not in configured MGA list.")
        else:
            self._prompt_for_mga()

        # Number of APs
        if 'kp_lkm' in self.cmd_args:
            try:
                num = int(self.cmd_args['kp_lkm'])
                limit = self.config.get('limit', 1000)
                if 1 <= num <= limit:
                    self.num_aps_to_generate = num
                else:
                    raise ValueError(f"Number of APs (kp_lkm) '{num}' out of range (1-{limit}).")
            except ValueError:
                raise ValueError(f"Invalid number for APs (kp_lkm): '{self.cmd_args['kp_lkm']}'.")
        else:
            self._prompt_for_num_aps()

        # AP Type
        ap_type_map = {'AG01': 'AG01', 'AG02': 'AG02'}
        if 'aptype' in self.cmd_args and self.cmd_args['aptype'] in ap_type_map:
            self.ap_type_code = ap_type_map[self.cmd_args['aptype']]
        elif 'aptype' in self.cmd_args:
            raise ValueError(f"Invalid AP Type code '{self.cmd_args['aptype']}'. Must be AG01 or AG02.")
        else:
            self._prompt_for_ap_type()

        # Remote Readable
        remote_map = {'0': '0', '1': '1'}
        if 'remote' in self.cmd_args and self.cmd_args['remote'] in remote_map:
            self.remote_readable_code = remote_map[self.cmd_args['remote']]
        elif 'remote' in self.cmd_args:
            raise ValueError(f"Invalid Remote Readable code '{self.cmd_args['remote']}'. Must be 0 or 1.")
        else:
            self._prompt_for_remote_readable()

        # Metering Method
        method_map = {'E13': 'E13', 'E14': 'E14', 'E16': 'E16'}
        if 'method' in self.cmd_args and self.cmd_args['method'] in method_map:
            self.metering_method_code = method_map[self.cmd_args['method']]
        elif 'method' in self.cmd_args:
            raise ValueError(f"Invalid Metering Method code '{self.cmd_args['method']}'. Must be E13, E14, or E16.")
        else:
            self._prompt_for_metering_method()

        # Final validation for command line args if any were provided but not all
        if self.cmd_args: # if any cmd_args were given, all must be present
            required_cmd_args = ['jvy', 'mga', 'kp_lkm', 'aptype', 'remote', 'method']
            missing_args = [arg for arg in required_cmd_args if arg not in self.cmd_args]
            if missing_args:
                raise ValueError(f"Missing command line arguments: {', '.join(missing_args)}. If using command line arguments, all must be provided: -j, -m, -l, -t, -r, -M.")


    def generate_ap_ids(self):
        """Generates a list of unique Accounting Point IDs."""
        if not self.selected_dso or self.num_aps_to_generate == 0:
            raise ValueError("DSO and number of APs must be set before generating IDs.")

        prefix = self.selected_dso[:8] # Assuming DSO ID is at least 8 chars

        id_range_start = self.config.get('id_range')
        if id_range_start is not None:
            if not isinstance(id_range_start, int) or id_range_start <= 0:
                 raise ValueError("Configuration error: id_range in fconfig.py must be a positive integer.")
            if id_range_start > 90000000: # Max value for the numeric part
                raise ValueError("Configuration error: id_range in fconfig.py exceeds the maximum value of 90000000.")
            current_id_num = id_range_start
        else:
            current_id_num = ra.randint(1, 90000000 - self.num_aps_to_generate) # Ensure range doesn't exceed max

        self.generated_ap_ids = []
        for _ in range(self.num_aps_to_generate):
            # Ensure the numeric part does not exceed 9 digits total (90,000,000 implies 8 digits, zfill(9) handles up to 9)
            # If current_id_num + i could exceed 99,999,999, this needs more careful handling
            # For now, assume id_range_start + num_aps_to_generate won't exceed this.
            ap_numeric_part = str(current_id_num).zfill(9)
            full_ap_base = prefix + ap_numeric_part
            self.generated_ap_ids.append(add_check_digit(int(full_ap_base)))
            current_id_num += 1
        print(f"Generated {len(self.generated_ap_ids)} AP IDs.")

    def _get_random_address(self):
        """Selects a random address and stores its parts."""
        if not self.osoitteet_list:
            # This should ideally be caught by _load_dependencies, but as a safeguard:
            print("Critical Error: Address list (osoitteet.txt) is empty or not loaded.")
            raise FileNotFoundError("Address list is empty.")

        address_line = ra.choice(self.osoitteet_list)
        try:
            parts = address_line.split(',')
            if len(parts) < 3: # Basic check for enough parts
                print(f"Warning: Malformed address line in osoitteet.txt: '{address_line}'. Using defaults.")
                self.current_address_details = {'zip': '00000', 'street': 'Default Street', 'city': 'Default City'}
            else:
                self.current_address_details = {
                    'zip': parts[0].strip(),
                    'street': parts[1].strip(),
                    'city': parts[2].strip()
                }
        except IndexError: # Should be caught by len(parts) check mostly
            print(f"Warning: Error parsing address line: '{address_line}'. Using defaults.")
            self.current_address_details = {'zip': '00000', 'street': 'Default Street', 'city': 'Default City'}


    def _get_random_supplier(self):
        """Returns a random supplier from the configured list."""
        # The check for empty dealers is in _load_config
        return ra.choice(self.config['dealers'])

    def produce_xml_for_ap(self, ap_id: str):
        """Produces an XML file for a single Accounting Point ID."""
        xml_template_path = 'libs/xml_template.xml'
        output_xml_dir = 'xml'

        try:
            if not os.path.exists(output_xml_dir):
                os.makedirs(output_xml_dir)

            tree = ET.parse(xml_template_path)

            # XML Namespace dictionary (consider making this a class attribute if used often)
            ns = {
                'ns2': 'urn:fi:Datahub:mif:masterdata:E58_MasterDataMPEvent:elements:v1', # For some reason original had this as ns2, ns5
                'ns3': 'urn:fi:Datahub:mif:common:HDR_Header:elements:v1'
                # Add other namespaces if needed based on template
            }

            # Helper for find with namespace
            def find_with_ns(element, path, namespaces):
                # Path might be like 'ns3:Identification'
                prefix, local_name = path.split(':')
                return element.find(f".//{{{namespaces[prefix]}}}{local_name}")

            # Fill XML fields - using a simplified find approach here. Original used fixed paths.
            # This needs to match the structure of xml_template.xml precisely.
            # The original script used a specific way of finding elements, often by
            # concatenating a namespace prefix with a tag name, and sometimes using an index.
            # ET.find() with .// searches anywhere. For specific paths, use them directly.
            # Namespace URIs:
            NS_HDR = "urn:fi:Datahub:mif:common:HDR_Header:elements:v1"
            NS_E58 = "urn:fi:Datahub:mif:masterdata:E58_MasterDataMPEvent:elements:v1"

            # Header elements
            tree.find(f".//{{{NS_HDR}}}Identification").text = gen_id(True)
            # Assuming PhysicalSenderEnergyParty and JuridicalSenderEnergyParty are complex elements
            # and their Identification child needs to be set.
            tree.find(f".//{{{NS_HDR}}}PhysicalSenderEnergyParty/{{{NS_HDR}}}Identification").text = self.selected_dso
            tree.find(f".//{{{NS_HDR}}}JuridicalSenderEnergyParty/{{{NS_HDR}}}Identification").text = self.selected_dso
            tree.find(f".//{{{NS_HDR}}}Creation").text = gen_timestamp()

            # E58 MasterDataMPEvent elements
            tree.find(f".//{{{NS_E58}}}StartOfOccurrence").text = gen_timestamp('True')

            # MeteringPointUsedDomainLocation - this tag appears multiple times.
            # Original: tree.find(ns2_orig+'MeteringPointUsedDomainLocation')[0].text = apoint
            # This implies the first <Identification> child of the first <MeteringPointUsedDomainLocation>
            mp_loc_elements = tree.findall(f".//{{{NS_E58}}}MeteringPointUsedDomainLocation")
            if mp_loc_elements: # Check if any found
                # First occurrence: Set AP ID
                id_tag = mp_loc_elements[0].find(f"{{{NS_E58}}}Identification")
                if id_tag is not None:
                    id_tag.text = ap_id
                else:
                    print(f"Warning: Could not find Identification for first MeteringPointUsedDomainLocation in template for AP {ap_id}")

                # Third occurrence (index 2): Set AP Type Code
                # Original: tree.find(ns2_orig+'MeteringPointUsedDomainLocation')[2].text = storage['type']
                # This implies the third <MeteringPointUsedDomainLocation> overall is for AP type.
                # And its text content (or a specific child) should be the type code.
                # This is highly dependent on template structure.
                # If it means the text of the element itself:
                if len(mp_loc_elements) > 2:
                     # Assuming it's not the text of the complex element, but a specific child like <Type>
                     type_tag = mp_loc_elements[2].find(f"{{{NS_E58}}}Type") # Example, adjust if actual tag is different
                     if type_tag is not None:
                         type_tag.text = self.ap_type_code
                     else:
                         # If the intention was to set the text of the main tag (unlikely for complex elements)
                         # mp_loc_elements[2].text = self.ap_type_code
                         print(f"Warning: Could not find <Type> sub-element for third MeteringPointUsedDomainLocation for AP {ap_id}")
            else:
                print(f"Warning: No MeteringPointUsedDomainLocation elements found in template for AP {ap_id}")


            mga_loc_element = tree.find(f".//{{{NS_E58}}}MeteringGridAreaUsedDomainLocation/{{{NS_E58}}}Identification")
            if mga_loc_element is not None:
                mga_loc_element.text = self.selected_mga
            else:
                print(f"Warning: MeteringGridAreaUsedDomainLocation/Identification not found for AP {ap_id}")

            # Address details
            self._get_random_address() # Sets self.current_address_details
            mp_addr_element = tree.find(f".//{{{NS_E58}}}MeteringPointAddress")
            if mp_addr_element is not None:
                street_name_tag = mp_addr_element.find(f"{{{NS_E58}}}StreetName")
                if street_name_tag is not None: street_name_tag.text = self.current_address_details['street']

                building_num_tag = mp_addr_element.find(f"{{{NS_E58}}}BuildingNumber")
                if building_num_tag is not None: building_num_tag.text = str(ra.randint(1,100))

                postcode_tag = mp_addr_element.find(f"{{{NS_E58}}}Postcode")
                if postcode_tag is not None: postcode_tag.text = self.current_address_details['zip']

                city_tag = mp_addr_element.find(f"{{{NS_E58}}}City")
                if city_tag is not None: city_tag.text = self.current_address_details['city']
            else:
                print(f"Warning: MeteringPointAddress element not found for AP {ap_id}")

            # Characteristics
            # Original: tree.find(ns2_orig+'MPDetailMeteringPointCharacteristic')[0].text = storage['remote']
            # Original: tree.find(ns2_orig+'MPDetailMeteringPointCharacteristic')[1].text = storage['method']
            # This implies there are at least two MPDetailMeteringPointCharacteristic elements.
            # And their text content (or a specific child) should be set.
            # Assuming the Nth child of the *document root* that matches, then its Nth child. This is fragile.
            # More robust: find all, then operate.
            char_elements = tree.findall(f".//{{{NS_E58}}}MPDetailMeteringPointCharacteristic")
            if len(char_elements) >= 1:
                # Assuming the first characteristic element is for remote readable status
                # And it has a sub-element like <Code> or <Value> that needs to be set.
                # If it's the text of the characteristic element itself: char_elements[0].text = self.remote_readable_code
                # This needs to be verified against xml_template.xml
                # Example: if it's a sub-element <Value>
                value_tag_remote = char_elements[0].find(f"{{{NS_E58}}}Code") # Or Value, Type, etc.
                if value_tag_remote is not None:
                    value_tag_remote.text = self.remote_readable_code
                else:
                    # Fallback: set text of the parent if no obvious child, though less likely correct
                    # char_elements[0].text = self.remote_readable_code
                    print(f"Warning: Could not find specific sub-tag for first MPDetailMeteringPointCharacteristic (remote) for AP {ap_id}")


            if len(char_elements) >= 2:
                # Assuming the second characteristic element is for metering method
                value_tag_method = char_elements[1].find(f"{{{NS_E58}}}Code") # Or Value, Type, etc.
                if value_tag_method is not None:
                    value_tag_method.text = self.metering_method_code
                else:
                    # char_elements[1].text = self.metering_method_code
                    print(f"Warning: Could not find specific sub-tag for second MPDetailMeteringPointCharacteristic (method) for AP {ap_id}")

            if not char_elements:
                 print(f"Warning: No MPDetailMeteringPointCharacteristic elements found for AP {ap_id}")


            output_file_path = os.path.join(output_xml_dir, f"apoint_{ap_id}.xml")
            tree.write(output_file_path, encoding='utf-8', xml_declaration=True)
            # print(f"Successfully wrote XML for {ap_id} to {output_file_path}")
            return True

        except FileNotFoundError:
            print(f"Error: XML template file '{xml_template_path}' not found.")
            return False
        except ET.ParseError as e:
            print(f"Error: Failed to parse XML template '{xml_template_path}': {e}")
            return False
        except IOError as e:
            print(f"Error: Failed to write XML to '{output_file_path}': {e}")
            return False
        except Exception as e: # Catch-all for other issues during XML production
            print(f"An unexpected error occurred during XML production for {ap_id}: {e}")
            return False

    def write_csv_summary(self):
        """Writes a summary of generated APs to kp.csv."""
        if not self.generated_ap_ids:
            print("No Accounting Point IDs were generated. Skipping CSV summary.")
            return

        csv_file_path = 'kp.csv'
        file_exists = os.path.isfile(csv_file_path)

        try:
            with open(csv_file_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists or os.path.getsize(csv_file_path) == 0:
                    writer.writerow([
                        'Accounting point', 'Metering Area', 'Supplier', 'DSO', 'MGA',
                        'ZIP', 'Street', 'City', 'AP type', 'Remote readable', 'Metering method'
                    ])

                if not self.selected_dso or not self.selected_mga: # Should be set by _determine_generation_parameters
                     print("Error: DSO or MGA not selected. Cannot write CSV summary accurately.")
                     return

                metering_area_prefix = self.selected_dso[:8] if self.selected_dso else "ERR_DSO"
                metering_area = metering_area_prefix + '00000000'

                for ap_id in self.generated_ap_ids:
                    # XML production for each AP is now separated.
                    # We rely on self.current_address_details being set by _get_random_address,
                    # which should be called if XML was produced.
                    # For CSV, we need an address even if XML failed, or skip.
                    # Let's call _get_random_address here to ensure it's fresh for each CSV row,
                    # matching the original intent where address was per-AP.
                    # However, produce_xml_for_ap already calls it.
                    # If XML fails, we might not have an address.
                    # Decision: If XML fails, we skip CSV row as we can't guarantee address consistency
                    # with what *would* have been in XML.

                    xml_success = self.produce_xml_for_ap(ap_id) # This also sets self.current_address_details

                    if xml_success:
                        supplier = self._get_random_supplier()
                        writer.writerow([
                            ap_id,
                            metering_area,
                            supplier,
                            self.selected_dso,
                            self.selected_mga,
                            self.current_address_details.get('zip', 'N/A'),
                            self.current_address_details.get('street', 'N/A'),
                            self.current_address_details.get('city', 'N/A'),
                            self.ap_type_code,
                            self.remote_readable_code,
                            self.metering_method_code
                        ])
                        # Ensure that current_address_details are populated for the CSV,
                        # even if XML production might have had issues unrelated to address fetching.
                        # However, produce_xml_for_ap already calls _get_random_address.
                        # If XML succeeded, current_address_details should be from that successful XML generation.
                        # If XML failed, self.current_address_details might be from a previous successful call
                        # or empty if no AP has succeeded yet.
                        # For consistency, if XML fails, we might want to call _get_random_address
                        # again for the CSV, or explicitly state that address details in CSV might be
                        # inconsistent if its corresponding XML failed.
                        # The current logic in skeleton is if xml_success, then write. This is safer.
                        print(f"Wrote entry for AP {ap_id} to CSV.")
                    else:
                        print(f"Skipping CSV entry for AP {ap_id} due to XML generation failure.")

            if self.generated_ap_ids: # Only print if there was an attempt to write data.
                print(f"CSV summary processing complete. Check '{csv_file_path}' for details.")

        except IOError as e:
            print(f"Error writing to CSV file '{csv_file_path}': {e}")
        except Exception as e: # Catch any other unexpected error during CSV writing
            print(f"An unexpected error occurred during CSV summary writing: {e}")
            # Optionally, re-raise or handle more gracefully depending on desired script behavior
            # For now, just printing the error.

    def run(self):
        """Main execution method for the generator."""
        try:
            print("Starting Accounting Point Generation...")
            self._determine_generation_parameters() # Handles its own ValueErrors for bad params
            self.generate_ap_ids() # Handles its own ValueErrors for bad id_range

            if not self.generated_ap_ids:
                print("No Accounting Point IDs were generated, likely due to configuration or input errors.")
                print("Accounting Point Generation aborted.")
                return

            self.write_csv_summary()
            print("Accounting Point Generation finished successfully.")

        except ValueError as e: # Catch errors from _determine_generation_parameters or generate_ap_ids
            print(f"A configuration or parameter error occurred: {e}")
            print("Accounting Point Generation aborted.")
            # No need to re-raise, as this is caught by the main __name__ block's handler
        except FileNotFoundError as e: # E.g. if osoitteet.txt was missing and _load_dependencies raised it.
            print(f"A required file was not found: {e}")
            print("Accounting Point Generation aborted.")
        # Other exceptions like ImportError for fconfig are handled by _load_config raising them
        # to be caught by the top-level handler in __main__


if __name__ == "__main__":
    cmd_opts_dict = {}
    # Define short and long options based on original script's getopt
    short_opts = "hl:j:m:t:r:M:"
    long_opts = ["kp_lkm=", "jvy=", "mga=", "aptype=", "remote=", "method="]

    try:
        # Parse command line arguments if any
        if len(sys.argv) > 1:
            # Check for help option first, as it doesn't require other args
            if '-h' in sys.argv[1:] or '--help' in sys.argv[1:]: # getopt doesn't handle -h well alone
                 print('Usage: kpgen.py [-j <DSO>] [-m <MGA>] [-l <num_aps>] [-t <type AG01|AG02>] [-r <remote 0|1>] [-M <method E13|E14|E16>]')
                 print('If any cmd args are used, all must be provided for non-interactive mode.')
                 print('-h: This help message.')
                 sys.exit(0)

            opts, args = getopt.getopt(sys.argv[1:], short_opts, long_opts)
            for opt, arg_val in opts:
                if opt in ('-l', '--kp_lkm'):
                    cmd_opts_dict['kp_lkm'] = arg_val
                elif opt in ('-j', '--jvy'):
                    cmd_opts_dict['jvy'] = arg_val
                elif opt in ('-m', '--mga'):
                    cmd_opts_dict['mga'] = arg_val
                elif opt in ('-t', '--aptype'):
                    cmd_opts_dict['aptype'] = arg_val
                elif opt in ('-r', '--remote'):
                    cmd_opts_dict['remote'] = arg_val
                elif opt in ('-M', '--method'):
                    cmd_opts_dict['method'] = arg_val

        generator = AccountingPointGenerator(cmd_args=cmd_opts_dict)
        generator.run()

    except getopt.GetoptError as e:
        print(f"Argument parsing error: {e}")
        print('Usage: kpgen.py [-j <DSO>] [-m <MGA>] [-l <num_aps>] [-t <type AG01|AG02>] [-r <remote 0|1>] [-M <method E13|E14|E16>]')
        sys.exit(2)
    except ImportError as e: # Catches fconfig import errors from _load_config
        print(f"Import error: {e}. Please ensure all dependencies are correctly installed and paths are correct.")
        sys.exit(1)
    except ValueError as e: # Catches config issues, invalid cmd args, etc.
        print(f"Configuration or Parameter Error: {e}")
        sys.exit(1)
    except FileNotFoundError as e: # Catches missing critical files like osoitteet.txt
        print(f"File Not Found Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user.")
        sys.exit(0)
    except EOFError: # If user cancels input prompts with Ctrl+D
        print("\n\nInput cancelled by user.")
        sys.exit(0)
    except Exception as e: # Catch-all for any other unexpected errors
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
