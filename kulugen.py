#!/usr/bin/python3
# -*- coding: utf-8 -*-

import datetime
import random as ra
import sys
import os # Changed from os.path to os for makedirs
import sqlite3
import csv
from os import name as os_name # aliased to avoid conflict with local 'name'
from getopt import getopt, GetoptError
from cmd import Cmd
import shutil # For potential future use, e.g. moving files
import xml.etree.ElementTree as ET

# --- Module Level Utilities ---

# Colors (remains unchanged)
if os_name == 'posix':
    bold, underline, reverse = '\u001b[1m', '\u001b[4m', '\u001b[7m'
    red, green, yellow, blue = '\u001b[31m', '\u001b[32m', '\u001b[33m', '\u001b[34m'
    magenta, cyan, white, reset = '\u001b[35m', '\u001b[36m', '\u001b[37m', '\u001b[0m'
else:
    red = green = yellow = blue = magenta = cyan = white = reset = bold = underline = reverse = ''

# Standard library imports first, then project-specific
try:
    from libs.kirjasto import gen_timestamp # add_check_digit is not used in this file
    # Removed: gen_id from kirjasto, will use a local _generate_session_id or similar for now
except ImportError:
    print(red + bold + 'Error: kirjasto.py missing or incomplete. Please consult Fingrid Datahub test team.' + reset)
    sys.exit(1)

# fconfig imports will be handled by ConsumptionGenerator._load_config

class Printer:
    """Simple utility to print data to stdout on one line, overwriting previous."""
    def __init__(self, data):
        sys.stdout.write("\r\x1b[K" + str(data))
        sys.stdout.flush()

# --- Main Classes ---

class ConsumptionGenerator:
    def __init__(self, cmd_args=None):
        self.cmd_args = cmd_args if cmd_args else {}
        self.config = {}  # Populated by _load_config

        self.db_path = 'fingrid.db'
        self.apoint_csv_path = 'kp.csv'
        self.rpoint_csv_path = 'rp.csv'
        self.xml_output_dir = 'xml/'
        self.log_dir = 'log/' # For future use if sending logic is added here, or for detailed logs

        # Replaces global 'storage' dictionary for data that changes per generation run
        # or is set by the interactive prompt for a single generation.
        self.transient_data = {
            'hours_to_generate': 24, # Default from original global storage
            'start_time_for_generation': "00:00", # Default
            'current_dso': None,
            'current_mga': None,
            'start_date_iso': None, # YYYY-MM-DDTHH:MM:SSZ
            'end_date_iso': None,   # YYYY-MM-DDTHH:MM:SSZ
            'metric': 'kWh',        # Default
            'metric_id': '8716867000030', # Default
            'last_generated_xml_path': None, # For the prompt to send
            # For rpoint specific transient data
            'current_rpoint_in_area': None,
            'current_rpoint_out_area': None,
        }

        self._load_config()
        self._ensure_dirs_exist()
        # self._ensure_db_tables_exist() # Call this when generation starts, or once if db is persistent

    def _load_config(self):
        """Loads configuration from libs.fconfig."""
        try:
            # These are directly used by consumption calculation or XML generation
            from libs.fconfig import prod_ap, prod_ep
            self.config['prod_ap'] = prod_ap
            self.config['prod_ep'] = prod_ep

            # These are for the 'send' functionality, which might be refactored later
            # For now, load them if InteractivePrompt.do_send needs them via generator.
            from libs.fconfig import url as fconfig_url, DSO as fconfig_DSO
            self.config['url'] = fconfig_url
            self.config['DSO_endpoints'] = fconfig_DSO

        except ImportError:
            print(red + bold + 'Error: libs.fconfig.py missing or incomplete.' + reset)
            # This is a critical error, so re-raise to be caught by main handler
            raise

    def _ensure_dirs_exist(self):
        """Ensures that XML output and log directories exist."""
        dirs_to_check = [self.xml_output_dir, self.log_dir]
        for dir_path in dirs_to_check:
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path)
                    print(f"Created directory: {dir_path}")
                except OSError as e:
                    print(red + f"Error creating directory {dir_path}: {e}" + reset)
                    # Depending on which dir failed, this might be critical
                    # For now, print error and continue; subsequent operations might fail

    @staticmethod
    def _generate_session_id(length=32):
        """Generates a random ID string (moved from global generate_id)."""
        # This was 'generate_id' in original, renamed for clarity if it's only for sessions.
        # If used for XML Identifications, 'generate_identifier' might be better.
        # For now, assuming it's for DB session_id primarily.
        return ''.join(ra.choice("abcdef1234567890") for _ in range(length))

    def run(self):
        """Main execution logic for the generator."""
        # Ensure DB tables are ready before any generation attempt.
        self._ensure_db_tables_exist()

        if self.cmd_args.get('interactive_mode'):
            prompt = InteractivePrompt(self) # Pass generator instance
            prompt.cmdloop()
        elif self.cmd_args.get('start_date_str') and self.cmd_args.get('num_days_str'):
            # Batch mode with command-line specified dates
            # transient_data for hours/start_time will use defaults unless overridden by future cmd args
            self._batch_generate_consumption(
                start_date_input=self.cmd_args['start_date_str'],
                num_days_input=self.cmd_args['num_days_str']
            )
        else:
            # Default batch mode (prompts for dates if not provided, generates for all APs)
            self._batch_generate_consumption(None, None)

        print("Consumption generation process finished.")

    def _db_connect(self):
        """Establishes a connection to the SQLite database."""
        try:
            # timeout option to prevent long waits if DB is locked
            conn = sqlite3.connect(self.db_path, timeout=10)
            return conn
        except sqlite3.Error as e:
            print(red + f"Database connection error to '{self.db_path}': {e}" + reset)
            raise # Propagate error to be handled by caller or main error handler

    def _ensure_db_tables_exist(self):
        """Ensures that the necessary database tables (apoint, rpoint) exist."""
        # SQL table creation queries (similar to original createSQL)
        # Using TEXT for types like INT that might store large numbers or have specific string formats from source.
        # Consider constraints and actual data types carefully.
        create_apoint_table_sql = """
        CREATE TABLE IF NOT EXISTS apoint (
            SESSION_ID     TEXT NOT NULL UNIQUE,
            APOINT_ID      TEXT,
            RPOINT_ID      TEXT, /* Should be NULL for apoint table, but kept for schema similarity if intended */
            R_IN           TEXT, /* Should be NULL for apoint table */
            R_OUT          TEXT, /* Should be NULL for apoint table */
            METERINGPOINT  TEXT,
            TIMESTAMP      TEXT NOT NULL,
            DSO            TEXT,
            MGA            TEXT,
            SUPPLIER       TEXT,
            KULUTUS        REAL, /* Using REAL for consumption values */
            AP_TYPE        TEXT,
            REMOTE_READ    TEXT,
            METHOD         TEXT,
            PRIMARY KEY(APOINT_ID, TIMESTAMP)
        );"""
        # Note: Original PRIMARY KEY was (APOINT_ID, TIMESTAMP) effectively,
        # though SESSION_ID was also UNIQUE. If APOINT_ID is the key with TIMESTAMP,
        # then RPOINT_ID etc. are attributes of that accounting point's reading.

        create_rpoint_table_sql = """
        CREATE TABLE IF NOT EXISTS rpoint (
            SESSION_ID     TEXT NOT NULL UNIQUE,
            APOINT_ID      TEXT, /* Should be NULL for rpoint table */
            RPOINT_ID      TEXT,
            R_IN           TEXT,
            R_OUT          TEXT,
            METERINGPOINT  TEXT, /* Usually NULL for rpoints, but kept if schema demands */
            TIMESTAMP      TEXT NOT NULL,
            DSO            TEXT,
            MGA            TEXT, /* MGA might not be directly applicable to rpoint, but DSO is */
            SUPPLIER       TEXT, /* Usually NULL for rpoints */
            KULUTUS        REAL,
            AP_TYPE        TEXT, /* Usually NULL for rpoints */
            REMOTE_READ    TEXT, /* Usually NULL for rpoints */
            METHOD         TEXT, /* Usually NULL for rpoints */
            PRIMARY KEY(RPOINT_ID, TIMESTAMP)
        );"""
        # Original key for rpoint was (RPOINT_ID, TIMESTAMP).

        try:
            with self._db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute(create_apoint_table_sql)
                cursor.execute(create_rpoint_table_sql)
                conn.commit()
        except sqlite3.Error as e:
            print(red + f"Database error during table creation: {e}" + reset)
            raise # Critical error, propagate

    def _generate_dates(self, start_date_str_input, num_days_str_input,
                        start_time_str=None, hours_per_day_val=None):
        """
        Generates a list of hourly timestamps based on inputs.
        Refactors original dategen and date_input logic.
        Sets self.transient_data['start_date_iso'] and self.transient_data['end_date_iso'].
        Returns list of formatted hourly timestamps or raises ValueError/TypeError.
        """
        # Use transient_data for defaults if not provided, which are set by prompt or batch defaults
        start_time_to_use = start_time_str if start_time_str is not None else self.transient_data['start_time_for_generation']
        hours_val = hours_per_day_val if hours_per_day_val is not None else self.transient_data['hours_to_generate']

        generated_timestamps = []

        try:
            num_days = 0
            if num_days_str_input is None: # Interactive or default batch mode, prompt for days
                 while num_days < 1:
                    days_input_str = input(f"Number of days (e.g., 1, 2, ...): ")
                    if not days_input_str.isdigit() or int(days_input_str) < 1:
                        print(red + "Invalid input. Please enter a positive integer for days." + reset)
                        continue
                    num_days = int(days_input_str)
            else: # Days provided (e.g., cmd line)
                if not num_days_str_input.isdigit() or int(num_days_str_input) < 1:
                    raise ValueError("Number of days must be a positive integer.")
                num_days = int(num_days_str_input)

            current_date_dt = None
            if start_date_str_input is None: # Interactive or default batch, prompt for date
                while True:
                    date_entry_str = input('Start date (e.g., 1.7.2019 or 01.07.2019): ')
                    try:
                        day, month, year = map(int, date_entry_str.split('.'))
                        current_date_dt = datetime.datetime(year, month, day)
                        break
                    except ValueError:
                        print(red + "Invalid date format. Please use dd.mm.yyyy or d.m.yyyy." + reset)
            else: # Date provided (e.g., cmd line or from prompt's stored value)
                try:
                    day, month, year = map(int, start_date_str_input.split('.'))
                    current_date_dt = datetime.datetime(year, month, day)
                except ValueError:
                    raise ValueError(f"Invalid start date format: '{start_date_str_input}'. Use dd.mm.yyyy.")

            # Incorporate start_time_to_use
            try:
                hour, minute = map(int, start_time_to_use.split(':'))
                start_datetime_dt = current_date_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                raise ValueError(f"Invalid start time format: '{start_time_to_use}'. Use HH:MM.")

            # Calculate end datetime based on total hours to generate
            # If hours_val is for the total duration (e.g. prompt set 'hours' directly)
            # Or if it's per day (then multiply by num_days)
            # Original logic: dategen took nro_days, and storage['hours'] was total hours if nro_days was None,
            # or hours per day if nro_days was set.
            # This new method is simpler: hours_val is total hours for the period defined by num_days * 24 (if hours_val is 24),
            # or a specific total number of hours if hours_val is different from 24.
            # Let's assume hours_val is total hours if it's not 24 and num_days is 1,
            # or it's hours per day if num_days > 1.
            # For simplicity, let's assume hours_val is the number of hours to generate per day specified by num_days.
            # The total duration is num_days * hours_val.
            # No, the original `dategen` with `storage['hours']` implies `hours_val` is total hours if `num_days` is effectively 1 for that mode.
            # If `num_days_input` is given (batch), then `hours_val` (default 24) is per day.
            # If called from prompt's single_kulutus, `self.days_val` is used for `num_days` and `self.hours_val` for total hours.

            # Let's clarify: this function generates `num_days` worth of data.
            # `hours_val` (from transient_data) determines how many hours are in *each* of those `num_days`.
            # The loop will iterate `num_days * hours_val` times, advancing by 1 hour each time.

            total_hours_to_generate = num_days * hours_val
            end_datetime_dt = start_datetime_dt + datetime.timedelta(hours=total_hours_to_generate)

            # Store ISO formatted start and end dates in transient_data for XML
            self.transient_data['start_date_iso'] = start_datetime_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            self.transient_data['end_date_iso'] = end_datetime_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            current_loop_dt = start_datetime_dt
            for _ in range(total_hours_to_generate):
                generated_timestamps.append(current_loop_dt.strftime("%d-%m-%YT%H:%M:%SZ")) # Format for DB/internal use
                current_loop_dt += datetime.timedelta(hours=1)

            return generated_timestamps

        except ValueError as e: # Catch parsing errors for dates/days/times
            print(red + f"Date/Time generation error: {e}" + reset)
            raise # Propagate to caller
        except Exception as e: # Catch any other unexpected error
            print(red + f"Unexpected error in _generate_dates: {e}" + reset)
            raise

    def _calculate_hourly_consumption(self, min_val_str=None, max_val_str=None,
                                      use_prod_value=False, prod_config_key=None):
        """
        Calculates a single hourly consumption value.
        Refactors original kulutus() logic.
        """
        if use_prod_value and prod_config_key and prod_config_key in self.config:
            prod_val = self.config[prod_config_key]
            if isinstance(prod_val, (int, float)):
                return float(prod_val) # Ensure it's a float
            else:
                print(yellow + f"Warning: Prod value for '{prod_config_key}' in fconfig is not a number. Using random." + reset)

        try:
            if min_val_str is not None and max_val_str is not None:
                min_val = int(min_val_str)
                max_val = int(max_val_str)
                if min_val < max_val:
                    return round(ra.randint(min_val, max_val) / 10.0, 1) # Original logic divides by 10
            # Default random generation if specific range is not valid or not provided
            return round(ra.randint(0, 100) / 10.0, 1) # Original default
        except ValueError:
            print(yellow + "Warning: Invalid min/max for consumption range. Using default random." + reset)
            return round(ra.randint(0, 100) / 10.0, 1) # Fallback to default

    def _insert_apoint_consumption_db(self, conn_cursor, data_dict):
        """Inserts a single accounting point consumption record into the database."""
        # Convert DD-MM-YYYYTHH:MM:SSZ from _generate_dates to YYYY-MM-DD HH:MM:SS for DB
        try:
            ts_parts = data_dict['timestamp'].split('T')
            date_parts = ts_parts[0].split('-') # DD, MM, YYYY
            time_part = ts_parts[1][:-1] # HH:MM:SS (remove Z)
            db_timestamp_str = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]} {time_part}"
        except IndexError:
             raise ValueError(f"Invalid timestamp format for DB insertion: {data_dict['timestamp']}")

        sql = """INSERT INTO apoint (
                    SESSION_ID, APOINT_ID, METERINGPOINT, TIMESTAMP, DSO, MGA, SUPPLIER,
                    KULUTUS, AP_TYPE, REMOTE_READ, METHOD
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        try:
            session_id = self._generate_session_id()
            params = (
                session_id,
                data_dict.get('apoint_id'),
                data_dict.get('meteringpoint'), # This needs to be fetched from kp.csv for the apoint_id
                db_timestamp_str,
                data_dict.get('dso'),
                data_dict.get('mga'),
                data_dict.get('supplier'),
                data_dict.get('kulutus'),
                data_dict.get('ap_type'),
                data_dict.get('remote_read'),
                data_dict.get('method', '').strip() # Ensure method is stripped
            )
            conn_cursor.execute(sql, params)
            return True # Indicate success
        except sqlite3.IntegrityError:
            # This means APOINT_ID + TIMESTAMP combination already exists
            print(cyan + f"Data for AP {data_dict.get('apoint_id')} at {db_timestamp_str} already in DB. Skipping." + reset)
            return False
        except sqlite3.Error as e:
            print(red + f"DB error inserting apoint consumption: {e}" + reset)
            # Depending on severity, might raise or just return False
            return False


    def _insert_rpoint_consumption_db(self, conn_cursor, data_dict):
        """Inserts a single exchange point consumption record into the database."""
        try:
            ts_parts = data_dict['timestamp'].split('T')
            date_parts = ts_parts[0].split('-')
            time_part = ts_parts[1][:-1]
            db_timestamp_str = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]} {time_part}"
        except IndexError:
             raise ValueError(f"Invalid timestamp format for DB insertion: {data_dict['timestamp']}")

        sql = """INSERT INTO rpoint (
                    SESSION_ID, RPOINT_ID, TIMESTAMP, DSO, R_IN, R_OUT, KULUTUS
                 ) VALUES (?, ?, ?, ?, ?, ?, ?)"""
        try:
            session_id = self._generate_session_id()
            params = (
                session_id,
                data_dict.get('rpoint_id'),
                db_timestamp_str,
                data_dict.get('dso'),
                data_dict.get('r_in'),
                data_dict.get('r_out'),
                data_dict.get('kulutus')
            )
            conn_cursor.execute(sql, params)
            return True
        except sqlite3.IntegrityError:
            print(cyan + f"Data for RP {data_dict.get('rpoint_id')} at {db_timestamp_str} already in DB. Skipping." + reset)
            return False
        except sqlite3.Error as e:
            print(red + f"DB error inserting rpoint consumption: {e}" + reset)
            return False

    def _get_apoint_details(self, apoint_id_to_find):
        """Fetches details for a specific accounting point from apoint_csv_path (kp.csv)."""
        if not os.path.exists(self.apoint_csv_path):
            print(red + f"Error: Accounting point CSV file not found: {self.apoint_csv_path}" + reset)
            # This is a critical issue for this operation.
            # kpgen should be run first. We won't try to run it from here.
            raise FileNotFoundError(f"{self.apoint_csv_path} not found. Please run kpgen first.")

        try:
            with open(self.apoint_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile) # Using DictReader for easier column access
                for row in reader:
                    # Assuming 'Accounting point' is the column name for AP IDs in kp.csv
                    if row.get('Accounting point') == apoint_id_to_find:
                        # Map CSV headers to a dictionary. Ensure keys match CSV headers.
                        # Example mapping based on typical kp.csv structure from kpgen.py
                        return {
                            'apoint_id': row.get('Accounting point'),
                            'meteringpoint': row.get('Metering Area'), # Or specific metering point ID if different
                            'supplier': row.get('Supplier'),
                            'dso': row.get('DSO'),
                            'mga': row.get('MGA'),
                            'ap_type': row.get('AP type'),
                            'remote_read': row.get('Remote readable'),
                            'method': row.get('Metering method')
                            # Add other fields if needed from kp.csv
                        }
            return None # AP ID not found
        except FileNotFoundError: # Should be caught by os.path.exists, but as safeguard
            print(red + f"Error: File not found during _get_apoint_details: {self.apoint_csv_path}" + reset)
            raise
        except Exception as e: # Catch other potential errors like CSV parsing issues
            print(red + f"Error reading or parsing {self.apoint_csv_path}: {e}" + reset)
            raise # Or return None if preferred to not halt everything

    def _get_rpoint_details(self, rpoint_id_to_find):
        """Fetches details for a specific exchange point from rpoint_csv_path (rp.csv)."""
        if not os.path.exists(self.rpoint_csv_path):
            print(red + f"Error: Exchange point CSV file not found: {self.rpoint_csv_path}" + reset)
            raise FileNotFoundError(f"{self.rpoint_csv_path} not found.")

        try:
            with open(self.rpoint_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile) # Assuming rp.csv also has headers
                # Headers in rp.csv from original luo_kulutus: ID,DSO,IN_AREA,OUT_AREA,MIN_KWH,MAX_KWH
                # Example: line.split(',')[0] for ID.
                for row in reader:
                    # Assuming first column in rp.csv is the RPOINT_ID (needs actual header name)
                    # Let's assume the header for rpoint ID is 'ID' or 'RPOINT_ID'
                    # This needs to match the actual CSV header in rp.csv
                    if row.get('ID') == rpoint_id_to_find or row.get('RPOINT_ID') == rpoint_id_to_find : # Check common names
                        return {
                            'rpoint_id': rpoint_id_to_find,
                            'dso': row.get('DSO'),
                            'in_area': row.get('IN_AREA'), # Or actual header name
                            'out_area': row.get('OUT_AREA'), # Or actual header name
                            'min_kwh': row.get('MIN_KWH'),   # For consumption calculation range
                            'max_kwh': row.get('MAX_KWH')    # For consumption calculation range
                        }
            return None # RP ID not found
        except FileNotFoundError:
            print(red + f"Error: File not found during _get_rpoint_details: {self.rpoint_csv_path}" + reset)
            raise
        except Exception as e:
            print(red + f"Error reading or parsing {self.rpoint_csv_path}: {e}" + reset)
            raise

    def _generate_apoint_xml(self, ap_id_val, date_str_for_filename_part, xml_data_points_str):
        """Generates the XML file for an accounting point's consumption data."""
        template_path = 'libs/kulutus_template.xml'
        # Ensure XML output directory exists (though _ensure_dirs_exist should handle it)
        if not os.path.exists(self.xml_output_dir): os.makedirs(self.xml_output_dir)

        # Construct output filename (similar to original)
        # date_str_for_filename_part should be like 'ddmmyyyy' from the first date of generation for that file
        out_file_name = f"kulutus_{ap_id_val}_{date_str_for_filename_part.replace('-', '')}.xml"
        out_file_path = os.path.join(self.xml_output_dir, out_file_name)

        self.transient_data['last_generated_xml_path'] = out_file_path # Store for prompt's send command

        try:
            # First, write the main structure by replacing placeholder in template
            # This part is from the original generate_apoint_xml (before finalize_xml)
            with open(template_path, 'r', encoding='utf-8') as infile, \
                 open(out_file_path, 'w', encoding='utf-8') as outfile:
                for row in infile:
                    if '<!-- Kulutus data points placeholder -->' in row: # Requires placeholder in template
                        outfile.write(xml_data_points_str)
                    else:
                        outfile.write(row)

            # Second, parse the newly created file and fill in header/context details (finalize_xml logic)
            tree = ET.parse(out_file_path)

            # Namespaces - must match those in kulutus_template.xml
            # These are examples; actual URIs should be verified from template
            ns_hdr = "urn:fi:Datahub:mif:common:HDR_Header:elements:v1"
            ns_e66_ts = "urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:v1" # Main E66 namespace
            ns_e66_elements = "urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:elements:v1"
            # ns_pec = "urn:fi:Datahub:mif:common:PEC_ProcessEnergyContext:elements:v1" # If needed

            # Using find with .// to be more resilient to path changes if structure is consistent below root
            # Header fields
            header_id_elem = tree.find(f".//{{{ns_hdr}}}Identification")
            if header_id_elem is not None: header_id_elem.text = self._generate_session_id(32) # Was generate_id()

            transaction_elem = tree.find(f".//{{{ns_e66_ts}}}Transaction/{{{ns_e66_ts}}}Identification") # Assuming Transaction has an Identification child
            if transaction_elem is not None: transaction_elem.text = self._generate_session_id(32)

            phys_sender_elem = tree.find(f".//{{{ns_hdr}}}PhysicalSenderEnergyParty/{{{ns_hdr}}}Identification")
            if phys_sender_elem is not None: phys_sender_elem.text = str(self.transient_data.get('current_dso', ''))

            jur_sender_elem = tree.find(f".//{{{ns_hdr}}}JuridicalSenderEnergyParty/{{{ns_hdr}}}Identification")
            if jur_sender_elem is not None: jur_sender_elem.text = str(self.transient_data.get('current_dso', ''))

            creation_elem = tree.find(f".//{{{ns_hdr}}}Creation")
            if creation_elem is not None: creation_elem.text = gen_timestamp() # From kirjasto

            # E66 TimeSeries elements
            start_elem = tree.find(f".//{{{ns_e66_elements}}}Start")
            if start_elem is not None: start_elem.text = self.transient_data.get('start_date_iso', '')

            end_elem = tree.find(f".//{{{ns_e66_elements}}}End")
            if end_elem is not None: end_elem.text = self.transient_data.get('end_date_iso', '')

            # ProductIncludedProductCharacteristic - assuming two occurrences
            prod_chars = tree.findall(f".//{{{ns_e66_elements}}}ProductIncludedProductCharacteristic/{{{ns_e66_elements}}}Identification")
            if len(prod_chars) > 0: prod_chars[0].text = self.transient_data.get('metric_id', '')
            if len(prod_chars) > 1: prod_chars[1].text = self.transient_data.get('metric', '') # Or this might be a different tag like 'Name' or 'Description'

            mp_used_loc_elem = tree.find(f".//{{{ns_e66_elements}}}MeteringPointUsedDomainLocation/{{{ns_e66_elements}}}Identification")
            if mp_used_loc_elem is not None: mp_used_loc_elem.text = str(ap_id_val)

            mga_used_loc_elem = tree.find(f".//{{{ns_e66_elements}}}MeteringGridAreaUsedDomainLocation/{{{ns_e66_elements}}}Identification")
            if mga_used_loc_elem is not None: mga_used_loc_elem.text = str(self.transient_data.get('current_mga', ''))
            
            tree.write(out_file_path, encoding='utf-8', xml_declaration=True)
            return out_file_path

        except FileNotFoundError:
            print(red + f"Error: XML template file '{template_path}' not found for AP {ap_id_val}." + reset)
        except ET.ParseError as e:
            print(red + f"Error parsing XML for AP {ap_id_val} from '{out_file_path}': {e}" + reset)
        except IOError as e:
            print(red + f"Error writing XML for AP {ap_id_val} to '{out_file_path}': {e}" + reset)
        except Exception as e:
            print(red + f"An unexpected error occurred during XML generation for AP {ap_id_val}: {e}" + reset)
        return None # Return None on failure


    def _generate_rpoint_xml(self, rp_id_val, date_str_for_filename_part, xml_data_points_str):
        """Generates the XML file for an exchange point's consumption data."""
        template_path = 'libs/rajapiste_template.xml' # Assuming this is the correct template
        if not os.path.exists(self.xml_output_dir): os.makedirs(self.xml_output_dir)

        out_file_name = f"rajapiste_{rp_id_val}_{date_str_for_filename_part.replace('-', '')}.xml"
        out_file_path = os.path.join(self.xml_output_dir, out_file_name)

        self.transient_data['last_generated_xml_path'] = out_file_path # Store for prompt's send command

        try:
            with open(template_path, 'r', encoding='utf-8') as infile, \
                 open(out_file_path, 'w', encoding='utf-8') as outfile:
                for row in infile:
                    if '<!-- Kulutus data points placeholder -->' in row: # Requires placeholder
                        outfile.write(xml_data_points_str)
                    else:
                        outfile.write(row)

            tree = ET.parse(out_file_path)

            ns_hdr = "urn:fi:Datahub:mif:common:HDR_Header:elements:v1"
            ns_e66_ts = "urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:v1"
            ns_e66_elements = "urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:elements:v1"

            header_id_elem = tree.find(f".//{{{ns_hdr}}}Identification")
            if header_id_elem is not None: header_id_elem.text = self._generate_session_id(32)

            transaction_elem = tree.find(f".//{{{ns_e66_ts}}}Transaction/{{{ns_e66_ts}}}Identification")
            if transaction_elem is not None: transaction_elem.text = self._generate_session_id(32)

            phys_sender_elem = tree.find(f".//{{{ns_hdr}}}PhysicalSenderEnergyParty/{{{ns_hdr}}}Identification")
            if phys_sender_elem is not None: phys_sender_elem.text = str(self.transient_data.get('current_dso', ''))

            jur_sender_elem = tree.find(f".//{{{ns_hdr}}}JuridicalSenderEnergyParty/{{{ns_hdr}}}Identification")
            if jur_sender_elem is not None: jur_sender_elem.text = str(self.transient_data.get('current_dso', ''))

            creation_elem = tree.find(f".//{{{ns_hdr}}}Creation")
            if creation_elem is not None: creation_elem.text = gen_timestamp()

            start_elem = tree.find(f".//{{{ns_e66_elements}}}Start")
            if start_elem is not None: start_elem.text = self.transient_data.get('start_date_iso', '')

            end_elem = tree.find(f".//{{{ns_e66_elements}}}End")
            if end_elem is not None: end_elem.text = self.transient_data.get('end_date_iso', '')

            # For RPoint, it's MeteringPointUsedDomainLocation for the RP ID itself
            rp_used_loc_elem = tree.find(f".//{{{ns_e66_elements}}}MeteringPointUsedDomainLocation/{{{ns_e66_elements}}}Identification")
            if rp_used_loc_elem is not None: rp_used_loc_elem.text = str(rp_id_val)

            # InArea and OutArea
            in_area_elem = tree.find(f".//{{{ns_e66_elements}}}InAreaUsedDomainLocation/{{{ns_e66_elements}}}Identification")
            if in_area_elem is not None: in_area_elem.text = str(self.transient_data.get('current_rpoint_in_area', ''))

            out_area_elem = tree.find(f".//{{{ns_e66_elements}}}OutAreaUsedDomainLocation/{{{ns_e66_elements}}}Identification")
            if out_area_elem is not None: out_area_elem.text = str(self.transient_data.get('current_rpoint_out_area', ''))

            tree.write(out_file_path, encoding='utf-8', xml_declaration=True)
            return out_file_path

        except FileNotFoundError:
            print(red + f"Error: XML template file '{template_path}' not found for RP {rp_id_val}." + reset)
        except ET.ParseError as e:
            print(red + f"Error parsing XML for RP {rp_id_val} from '{out_file_path}': {e}" + reset)
        except IOError as e:
            print(red + f"Error writing XML for RP {rp_id_val} to '{out_file_path}': {e}" + reset)
        except Exception as e:
            print(red + f"An unexpected error occurred during XML generation for RP {rp_id_val}: {e}" + reset)
        return None


    def _batch_generate_consumption(self, start_date_input, num_days_input,
                                  target_apoint_id=None, metering_state_code=''):
        """
        Orchestrates the consumption data generation for APs and RPs.
        Can run for a single AP/RP or all APs/RPs found in CSV files.
        """
        print(cyan + "Starting consumption generation batch..." + reset)
        try:
            # Use transient_data for hours/start_time which are set by prompt or defaults
            hourly_timestamps = self._generate_dates(
                start_date_str_input=start_date_input,
                num_days_str_input=num_days_input
                # start_time_str and hours_per_day_val will use defaults from self.transient_data
                # if not overridden by more specific logic (e.g. prompt setting them directly)
            )
            if not hourly_timestamps:
                print(red + "Failed to generate date range. Aborting batch." + reset)
                return

            first_date_for_filename = hourly_timestamps[0].split('T')[0] # Get DD-MM-YYYY part

        except (ValueError, TypeError) as e:
            print(red + f"Error in date setup: {e}. Aborting batch." + reset)
            return

        try:
            with self._db_connect() as conn: # Ensure DB connection is managed per batch
                cursor = conn.cursor()

                if target_apoint_id: # Single AP generation mode
                    print(f"Generating for single AP: {target_apoint_id}")
                    ap_details = self._get_apoint_details(target_apoint_id)
                    if not ap_details:
                        print(red + f"Details for AP {target_apoint_id} not found. Cannot generate." + reset)
                        return

                    self.transient_data['current_dso'] = ap_details.get('dso')
                    self.transient_data['current_mga'] = ap_details.get('mga')
                    # Other transient_data like metric, metric_id are already set by __init__ or prompt

                    xml_data_points_str = ""
                    obs_count = 0
                    for ts_str in hourly_timestamps:
                        obs_count += 1
                        consumption = self._calculate_hourly_consumption(
                            use_prod_value=bool(self.config.get('prod_ap')), # True if prod_ap has a value
                            prod_config_key='prod_ap'
                        )
                        # Accumulate XML data points string
                        # Original format: <urn4:OBS><urn4:SEQ>{}</urn4:SEQ><urn4:EOBS><urn4:QTY>{}</urn4:QTY><urn4:QQ>{}</urn4:QQ></urn4:EOBS></urn4:OBS>
                        # Assuming urn4 is the namespace for E66_EnergyTimeSeries:elements
                        # This structure needs to be exact. For now, using a simplified placeholder for data points.
                        # The actual XML structure for observations should be confirmed from template.
                        xml_data_points_str += f"\t\t\t\t\t\t\t\t<Observation>\n\t\t\t\t\t\t\t\t\t<Sequence>{obs_count}</Sequence>\n\t\t\t\t\t\t\t\t\t<EnergyObservation>\n\t\t\t\t\t\t\t\t\t\t<Quantity>{consumption}</Quantity>\n\t\t\t\t\t\t\t\t\t\t<QualityCode>{metering_state_code}</QualityCode>\n\t\t\t\t\t\t\t\t\t</EnergyObservation>\n\t\t\t\t\t\t\t\t</Observation>\n"

                        db_data = {**ap_details, 'timestamp': ts_str, 'kulutus': consumption}
                        self._insert_apoint_consumption_db(cursor, db_data)

                    conn.commit() # Commit after all DB operations for this AP

                    if xml_data_points_str:
                        generated_xml_path = self._generate_apoint_xml(target_apoint_id, first_date_for_filename, xml_data_points_str)
                        if generated_xml_path:
                            Printer(f"AP {target_apoint_id}: XML generated at {generated_xml_path}")
                        else:
                            Printer(f"AP {target_apoint_id}: XML generation failed.")
                    Printer(f"AP {target_apoint_id} processing complete.\n")

                else: # Batch mode for all APs and RPs
                    # --- Accounting Points (kp.csv) ---
                    if not os.path.exists(self.apoint_csv_path):
                        print(yellow + f"Warning: {self.apoint_csv_path} not found. Skipping accounting point consumption." + reset)
                    else:
                        print(cyan + f"Processing Accounting Points from {self.apoint_csv_path}..." + reset)
                        with open(self.apoint_csv_path, 'r', newline='', encoding='utf-8') as ap_csvfile:
                            ap_reader = csv.DictReader(ap_csvfile)
                            for row_num, ap_row in enumerate(ap_reader):
                                current_ap_id = ap_row.get('Accounting point')
                                if not current_ap_id:
                                    print(yellow + f"Warning: Skipping row {row_num+2} in {self.apoint_csv_path} due to missing AP ID." + reset)
                                    continue

                                Printer(f"Processing AP: {current_ap_id}...")
                                self.transient_data['current_dso'] = ap_row.get('DSO')
                                self.transient_data['current_mga'] = ap_row.get('MGA')
                                # Populate other needed ap_details for DB insert from ap_row
                                ap_db_details_base = {
                                    'apoint_id': current_ap_id,
                                    'meteringpoint': ap_row.get('Metering Area'),
                                    'supplier': ap_row.get('Supplier'),
                                    'dso': ap_row.get('DSO'),
                                    'mga': ap_row.get('MGA'),
                                    'ap_type': ap_row.get('AP type'),
                                    'remote_read': ap_row.get('Remote readable'),
                                    'method': ap_row.get('Metering method')
                                }

                                xml_data_points_str = ""
                                obs_count = 0
                                for ts_str in hourly_timestamps:
                                    obs_count += 1
                                    consumption = self._calculate_hourly_consumption(
                                        use_prod_value=bool(self.config.get('prod_ap')),
                                        prod_config_key='prod_ap'
                                    )
                                    xml_data_points_str += f"\t\t\t\t\t\t\t\t<Observation>\n\t\t\t\t\t\t\t\t\t<Sequence>{obs_count}</Sequence>\n\t\t\t\t\t\t\t\t\t<EnergyObservation>\n\t\t\t\t\t\t\t\t\t\t<Quantity>{consumption}</Quantity>\n\t\t\t\t\t\t\t\t\t\t<QualityCode>{metering_state_code}</QualityCode>\n\t\t\t\t\t\t\t\t\t</EnergyObservation>\n\t\t\t\t\t\t\t\t</Observation>\n"

                                    db_data = {**ap_db_details_base, 'timestamp': ts_str, 'kulutus': consumption}
                                    self._insert_apoint_consumption_db(cursor, db_data)

                                conn.commit() # Commit per AP
                                if xml_data_points_str:
                                    self._generate_apoint_xml(current_ap_id, first_date_for_filename, xml_data_points_str)
                                Printer(f"AP {current_ap_id} processing complete.\n")
                        sys.stdout.write("\n") # Newline after Printer loop

                    # --- Exchange Points (rp.csv) ---
                    if not os.path.exists(self.rpoint_csv_path):
                        print(yellow + f"Warning: {self.rpoint_csv_path} not found. Skipping exchange point consumption." + reset)
                    else:
                        print(cyan + f"Processing Exchange Points from {self.rpoint_csv_path}..." + reset)
                        with open(self.rpoint_csv_path, 'r', newline='', encoding='utf-8') as rp_csvfile:
                            rp_reader = csv.DictReader(rp_csvfile)
                            # Expected headers in rp.csv: ID,DSO,IN_AREA,OUT_AREA,MIN_KWH,MAX_KWH (example)
                            for row_num, rp_row in enumerate(rp_reader):
                                current_rp_id = rp_row.get('ID') or rp_row.get('RPOINT_ID') # Check common names
                                if not current_rp_id:
                                    print(yellow + f"Warning: Skipping row {row_num+2} in {self.rpoint_csv_path} due to missing RP ID." + reset)
                                    continue

                                Printer(f"Processing RP: {current_rp_id}...")
                                self.transient_data['current_dso'] = rp_row.get('DSO')
                                self.transient_data['current_rpoint_in_area'] = rp_row.get('IN_AREA')
                                self.transient_data['current_rpoint_out_area'] = rp_row.get('OUT_AREA')
                                rp_min_kwh = rp_row.get('MIN_KWH')
                                rp_max_kwh = rp_row.get('MAX_KWH')

                                rp_db_details_base = {
                                    'rpoint_id': current_rp_id,
                                    'dso': rp_row.get('DSO'),
                                    'r_in': rp_row.get('IN_AREA'),
                                    'r_out': rp_row.get('OUT_AREA')
                                }

                                xml_data_points_str = ""
                                obs_count = 0
                                for ts_str in hourly_timestamps:
                                    obs_count += 1
                                    consumption = self._calculate_hourly_consumption(
                                        min_val_str=rp_min_kwh, max_val_str=rp_max_kwh,
                                        use_prod_value=bool(self.config.get('prod_ep')),
                                        prod_config_key='prod_ep'
                                    )
                                    # Note: RPoint XML structure might be simpler or different for QualityCode
                                    xml_data_points_str += f"\t\t\t\t\t\t\t\t<Observation>\n\t\t\t\t\t\t\t\t\t<Sequence>{obs_count}</Sequence>\n\t\t\t\t\t\t\t\t\t<EnergyObservation>\n\t\t\t\t\t\t\t\t\t\t<Quantity>{consumption}</Quantity>\n\t\t\t\t\t\t\t\t\t\t{'' if not metering_state_code else f'<QualityCode>{metering_state_code}</QualityCode>'}\n\t\t\t\t\t\t\t\t\t</EnergyObservation>\n\t\t\t\t\t\t\t\t</Observation>\n"

                                    db_data = {**rp_db_details_base, 'timestamp': ts_str, 'kulutus': consumption}
                                    self._insert_rpoint_consumption_db(cursor, db_data)

                                conn.commit() # Commit per RP
                                if xml_data_points_str:
                                    self._generate_rpoint_xml(current_rp_id, first_date_for_filename, xml_data_points_str)
                                Printer(f"RP {current_rp_id} processing complete.\n")
                        sys.stdout.write("\n") # Newline after Printer loop

        except FileNotFoundError as e: # Catch if CSVs are not found when attempting to open
            print(red + f"Error: Required CSV file not found: {e}. Aborting batch." + reset)
        except sqlite3.Error as e:
            print(red + f"Database error during batch processing: {e}. Batch may be incomplete." + reset)
        except Exception as e:
            print(red + f"An unexpected error occurred during batch processing: {e}" + reset)
            import traceback
            traceback.print_exc()

    def get_all_apoint_ids_from_csv(self):
        """Reads apoint_csv_path and returns a list of Accounting Point IDs."""
        ap_ids = []
        if not os.path.exists(self.apoint_csv_path):
            # This was the original behavior of kpaikat() if kp.csv missing, it would run kpgen.
            # That's too much of a side effect for a 'list' or data gathering command.
            # Better to inform the user and let them run kpgen if needed.
            print(magenta + f"{self.apoint_csv_path} not found. Please run kpgen.py to generate accounting points first." + reset)
            return []

        try:
            with open(self.apoint_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if row.get('Accounting point'):
                        ap_ids.append(row['Accounting point'])
            return ap_ids
        except Exception as e:
            print(red + f"Error reading AP IDs from {self.apoint_csv_path}: {e}" + reset)
            return []

# Removed send_xml_file placeholder from ConsumptionGenerator, as InteractivePrompt.do_send handles it.

class InteractivePrompt(Cmd):
    def __init__(self, generator_instance: ConsumptionGenerator):
        super().__init__()
        self.generator = generator_instance # Store instance of ConsumptionGenerator
        self.prompt = green + '<kulugen> ' + reset
        self.intro = cyan + '\nWelcome to Kulugen Interactive Mode!\n' + \
                     'Type ? or help to list commands.\n' + \
                     'Default values are shown in (parentheses).\n' + reset

        # Attributes to hold settings from 'set' commands (mirroring original Prompt)
        self.apoint = None
        self.supplier = None # For display, derived from apoint selection
        self.dso = None      # For display and potential use in send, derived from apoint selection
        self.mga = None      # For display, derived from apoint selection

        self.startdate_str = None # Format: dd.mm.yyyy
        self.days_val = 0         # Number of days
        self.hours_val = 24       # Hours to generate (default 24)
        self.starttime_str = "00:00" # Start time for generation (default 00:00)
        self.metering_state_code = '' # Metering state code (e.g., Z01)
        self.metric_name = 'kWh'
        self.metric_id_val = '8716867000030' # Default metric ID for kWh

        # For 'list_apoint' command
        self._cached_apoint_ids = None # Can be used to cache if CSV reading is slow

    def do_list_apoint(self, arg):
        """Lists all accounting points found in the kp.csv file."""
        # Invalidate cache if arg is 'refresh' or similar, or just always re-read for simplicity
        # For now, always re-read.
        ap_ids = self.generator.get_all_apoint_ids_from_csv()
        if not ap_ids:
            print(magenta + "No accounting points found or kp.csv is missing/empty." + reset)
            return

        print(cyan + "Available Accounting Points:" + reset)
        # Simple column display for now
        col_width = 20 # Adjust as needed
        num_cols = 4   # Adjust as needed
        for i, ap_id in enumerate(ap_ids):
            print(f"{ap_id:{col_width}}", end="")
            if (i + 1) % num_cols == 0:
                print()
        if len(ap_ids) % num_cols != 0: # Newline if last row wasn't full
            print()
        print(cyan + f"\nTotal: {len(ap_ids)}" + reset)

    def help_list_apoint(self):
        print("Syntax: list_apoint")
        print("-- Lists all available accounting points from kp.csv.")

    def do_reset(self, arg):
        """Resets all prompt settings to their default values."""
        self.apoint = None
        self.supplier = None
        self.dso = None
        self.mga = None
        self.startdate_str = None
        self.days_val = 0
        self.hours_val = 24
        self.starttime_str = "00:00"
        self.metering_state_code = ''
        self.metric_name = 'kWh'
        self.metric_id_val = '8716867000030'

        # Reset relevant transient_data in the generator instance as well
        self.generator.transient_data['hours_to_generate'] = 24
        self.generator.transient_data['start_time_for_generation'] = "00:00"
        self.generator.transient_data['metric'] = 'kWh'
        self.generator.transient_data['metric_id'] = '8716867000030'
        self.generator.transient_data['last_generated_xml_path'] = None

        self.prompt = green + '<kulugen> ' + reset # Reset prompt appearance
        print(cyan + "All interactive prompt settings have been reset to defaults." + reset)

    def help_reset(self):
        print("Syntax: reset")
        print("-- Resets all settings in the interactive prompt to their default values.")

    # Placeholder for do_single_kulutus
    def do_single_kulutus(self, arg):
        """Generates consumption for the currently set single accounting point and parameters."""
        # print(yellow + "Placeholder: do_single_kulutus called." + reset)
        if not self.apoint:
            print(red + "Error: Accounting Point not set. Use 'set apoint <id>' first." + reset)
            return
        if not self.startdate_str:
            print(red + "Error: Start Date not set. Use 'set startdate <dd.mm.yyyy>'." + reset)
            return
        if self.days_val <= 0:
            # Check if hours_val is set for a sub-day generation
            if self.hours_val <= 0 or self.hours_val >= 24 : # if hours is also not a valid sub-day period
                 print(red + "Error: Number of Days (or specific Hours) not set correctly. Use 'set days <n>' or 'set hours <h>'." + reset)
                 return
            elif self.hours_val > 0 and self.hours_val < 24 :
                 # This is a sub-day generation, set days_val to 1 for _generate_dates logic.
                 # The actual duration is handled by hours_val in transient_data.
                 # _generate_dates uses num_days * hours_val for total hours.
                 # So if we want to generate for X hours total, and days_val is 1, hours_val should be X.
                 # If self.days_val is 0 from 'set days 0', but 'set hours X' was used,
                 # it means user wants to generate for X total hours, starting on startdate.
                 # _generate_dates will use num_days=1 (implicit if days_val=0 passed as num_days_str_input=None to it, or explicit)
                 # and hours_per_day_val = self.hours_val.
                 # For now, let's ensure days_val is at least 1 if hours_val implies a full day or more.
                 # If hours_val is < 24, it's fine for days_val to be 1.
                 # The logic in _generate_dates might need to be robust to days_val=0 if hours_val is the primary driver.
                 # Current _generate_dates requires days_val >= 1 if num_days_str_input is None.
                 # Let's assume if hours_val is set to <24, days_val should be 1.
                 if self.days_val == 0: self.days_val = 1 # Default to 1 day if generating specific hours.

        print(cyan + f"Preparing to generate consumption for AP: {self.apoint}" + reset)
        print(f"  Start Date: {self.startdate_str}, Days: {self.days_val}, Start Time: {self.starttime_str}, Hours/Day: {self.hours_val}")
        print(f"  Metric: {self.metric_name} ({self.metric_id_val}), State: '{self.metering_state_code if self.metering_state_code else 'OK'}'")

        # Update generator's transient_data with prompt's current settings
        self.generator.transient_data['hours_to_generate'] = self.hours_val # This is hours_per_day for _generate_dates
        self.generator.transient_data['start_time_for_generation'] = self.starttime_str
        self.generator.transient_data['metric'] = self.metric_name
        self.generator.transient_data['metric_id'] = self.metric_id_val
        # DSO and MGA for XML will be taken from the selected AP's details by _batch_generate_consumption

        self.generator._batch_generate_consumption(
            start_date_input=self.startdate_str,
            num_days_str_input=str(self.days_val),
            target_apoint_id=self.apoint,
            metering_state_code=self.metering_state_code # Pass the code directly
        )
        if self.generator.transient_data.get('last_generated_xml_path'):
            print(green + f"Generated XML: {self.generator.transient_data['last_generated_xml_path']}" + reset)
        else:
            print(red + "XML generation may have failed or was skipped." + reset)

    # --- `set` command and its helpers ---
    _set_commands = ('apoint', 'startdate', 'days', 'hours', 'starttime', 'metering_state', 'metric', 'mga')
    # (Note: 'mga' was in original set_commands, but its direct utility in kulugen prompt was less clear
    # as MGA for XML is derived from apoint's CSV data. Keeping for compatibility if some logic used it.)

    def do_set(self, arg_str):
        """
        Sets various parameters for consumption generation.
        Usage: set <parameter> <value>
        Type 'set' to see current values.
        Type 'help set' for more details.
        """
        params = arg_str.split()
        if not params: # Show current settings
            self._show_current_settings()
            return

        setting = params[0].lower()
        if setting not in self._set_commands:
            print(red + f"Invalid setting '{setting}'. Type 'help set' for available parameters." + reset)
            return

        if len(params) < 2 and setting != 'apoint': # Apoint can be listed without value
             print(red + f"Missing value for setting '{setting}'." + reset)
             return
        
        value = params[1] if len(params) > 1 else None

        try:
            if setting == 'apoint':
                self._set_apoint(value)
            elif setting == 'startdate':
                self._set_startdate(value)
            elif setting == 'days':
                self._set_days(value)
            elif setting == 'hours':
                self._set_hours(value)
            elif setting == 'starttime':
                self._set_starttime(value)
            elif setting == 'metering_state':
                self._set_metering_state(value)
            elif setting == 'metric':
                self._set_metric(value)
            elif setting == 'mga': # MGA is usually derived, but allow display/override if needed
                self._set_mga(value)
        except ValueError as e:
            print(red + f"Error setting '{setting}': {e}" + reset)

    def _show_current_settings(self):
        print(cyan + "Current settings for consumption generation:" + reset)
        print(f"  Accounting Point (apoint): {green}{self.apoint if self.apoint else 'Not set'}{reset}")
        print(f"  Derived DSO:             {green}{self.dso if self.dso else 'N/A'}{reset}")
        print(f"  Derived MGA:             {green}{self.mga if self.mga else 'N/A'}{reset}")
        print(f"  Supplier:                {green}{self.supplier if self.supplier else 'N/A'}{reset}")
        print(f"  Start Date (startdate):  {green}{self.startdate_str if self.startdate_str else 'Not set'}{reset}")
        print(f"  Number of Days (days):   {green}{self.days_val}{reset}")
        print(f"  Hours per Day (hours):   {green}{self.hours_val}{reset} (Total hours for generation: {self.days_val * self.hours_val if self.days_val > 0 else self.hours_val})")
        print(f"  Start Time (starttime):  {green}{self.starttime_str}{reset}")
        print(f"  Metering State (state):  {green}{self.metering_state_code if self.metering_state_code else 'OK'}{reset}")
        print(f"  Metric (metric):         {green}{self.metric_name} (ID: {self.metric_id_val}){reset}")

    def _require_apoint_set(self, for_setting):
        if not self.apoint:
            raise ValueError(f"Accounting Point (apoint) must be set before setting '{for_setting}'.")
        return True

    def _set_apoint(self, ap_id_str):
        if not ap_id_str:
            print(green + "Usage: set apoint <apoint_id>" + reset)
            print(green + "Example: set apoint 123456789012345678" + reset)
            print(green + "Use 'list_apoint' to see available IDs." + reset)
            return

        if not (len(ap_id_str) == 18 and ap_id_str.isdigit()):
            # Basic validation, actual check is via _get_apoint_details
             print(magenta + f"'{ap_id_str}' is not a valid AP ID format (must be 18 digits)." + reset)
             return

        details = self.generator._get_apoint_details(ap_id_str)
        if details:
            self.apoint = ap_id_str # Store as string
            self.supplier = details.get('supplier')
            self.dso = details.get('dso')
            self.mga = details.get('mga')
            self.prompt = green + f"<kulugen AP:{self.apoint}> " + reset
            print(cyan + f"Accounting Point set to: {self.apoint}" + reset)
            print(f"  DSO: {self.dso}, MGA: {self.mga}, Supplier: {self.supplier}")
        else:
            print(magenta + f"Accounting Point ID '{ap_id_str}' not found in {self.generator.apoint_csv_path}." + reset)
            # Do not clear self.apoint if new one is invalid, keep old one.

    def _set_startdate(self, date_str):
        self._require_apoint_set('startdate')
        try:
            day, month, year = map(int, date_str.split('.'))
            datetime.datetime(year, month, day) # Validate date
            self.startdate_str = f"{day:02d}.{month:02d}.{year:04d}"
            print(cyan + f"Start Date set to: {self.startdate_str}" + reset)
        except ValueError:
            raise ValueError("Invalid date format. Use dd.mm.yyyy.")

    def _set_days(self, days_str):
        self._require_apoint_set('days')
        try:
            days = int(days_str)
            if days < 0: raise ValueError("Days cannot be negative.") # Allow 0 if hours is used
            self.days_val = days
            print(cyan + f"Number of Days set to: {self.days_val}" + reset)
            if days == 0 and self.hours_val == 24:
                 print(yellow+"Warning: Days set to 0. If you want to generate for specific hours less than a day, use 'set hours <h>'."+reset)
            elif days > 0 and self.hours_val != 24:
                 print(yellow+f"Note: Generating for {self.days_val} day(s), each with {self.hours_val} hour(s) of data."+reset)

        except ValueError:
            raise ValueError("Invalid number for days. Must be an integer >= 0.")

    def _set_hours(self, hours_str):
        self._require_apoint_set('hours')
        try:
            hours = int(hours_str)
            if not (0 < hours <= 10000) : # Original limit was 1-10000
                raise ValueError("Hours must be between 1 and 10000.")
            self.hours_val = hours
            print(cyan + f"Hours per day set to: {self.hours_val}" + reset)
            if self.days_val == 0 and self.hours_val < 24:
                print(yellow + "Note: Generating for a partial day. 'days' is effectively 1 for this generation."+reset)
            elif self.days_val > 0 and self.hours_val !=24:
                 print(yellow+f"Note: Generating for {self.days_val} day(s), each with {self.hours_val} hour(s) of data."+reset)

        except ValueError:
            raise ValueError("Invalid number for hours. Must be an integer (1-10000).")

    def _set_starttime(self, time_str):
        self._require_apoint_set('starttime')
        try:
            hour, minute = map(int, time_str.split(':'))
            datetime.time(hour, minute) # Validate time
            self.starttime_str = f"{hour:02d}:{minute:02d}"
            print(cyan + f"Start Time set to: {self.starttime_str}" + reset)
        except ValueError:
            raise ValueError("Invalid time format. Use HH:MM.")

    def _set_metering_state(self, state_key_str):
        self._require_apoint_set('metering_state')
        # States from original Prompt.do_set
        states_map = {'OK': '', 'Revised': 'Z01', 'Uncertain': 'Z02', 'Estimated': '99'}
        if state_key_str.capitalize() in states_map:
            self.metering_state_code = states_map[state_key_str.capitalize()]
            print(cyan + f"Metering State set to: {state_key_str.capitalize()} (Code: '{self.metering_state_code if self.metering_state_code else 'OK'}')" + reset)
        else:
            valid_states = ", ".join(states_map.keys())
            raise ValueError(f"Invalid metering state '{state_key_str}'. Valid states: {valid_states}.")

    def _set_metric(self, metric_str):
        self._require_apoint_set('metric')
        # Metrics from original Prompt.do_set
        metrics_map = {
            'Wh': '8716867000030', 'kWh': '8716867000030', 'MWh': '8716867000030',
            'GWh': '8716867000030', 'varh': '8716867000139', 'kvarh': '8716867000139',
            'Mvarh': '8716867000139'
        }
        if metric_str in metrics_map:
            self.metric_name = metric_str
            self.metric_id_val = metrics_map[metric_str]
            print(cyan + f"Metric set to: {self.metric_name} (ID: {self.metric_id_val})" + reset)
        else:
            valid_metrics = ", ".join(metrics_map.keys())
            raise ValueError(f"Invalid metric '{metric_str}'. Valid states: {valid_metrics}.")

    def _set_mga(self, mga_str):
        # MGA is usually derived from AP. This allows manual override for some reason if needed by original logic.
        # Or it's just for display consistency with old prompt.
        # For now, just sets it. If AP is set, this will be overridden by AP's MGA.
        if not (len(mga_str) == 16 and mga_str.isdigit()): # Example validation
             print(magenta + f"'{mga_str}' is not a valid MGA format (must be 16 digits)." + reset)
             return
        self.mga = mga_str # This is prompt's local MGA, distinct from AP's MGA.
        print(cyan + f"Prompt MGA manually set to: {self.mga}. This may be overridden by 'set apoint'." + reset)

    def help_set(self):
        print(cyan + "Usage: set <parameter> <value>" + reset)
        print("Sets parameters for consumption data generation. Type 'set' to see current values.")
        print("Available parameters:")
        for cmd_item in self._set_commands:
            # Could add more detailed help per item here later
            print(f"  {cmd_item:<15} - Set {cmd_item.replace('_', ' ')}")
        print("\nExample: set apoint 123456789012345678")
        print("         set startdate 01.01.2023")
        print("         set days 7")
        print("         set metering_state Estimated")
        print(magenta + "Note: 'apoint' must typically be set first." + reset)

    def complete_set(self, text, line, begidx, endidx):
        """Auto-completes the 'set' command parameters."""
        if line.count(' ') == 1: # Completing the parameter name
            return [s + ' ' for s in self._set_commands if s.startswith(text)]

        # Add more specific completion for values if needed later
        # For example, for 'set metering_state', complete with OK, Revised, etc.
        # if line.startswith("set metering_state "):
        #    mstates = ['OK', 'Revised', 'Uncertain', 'Estimated']
        #    return [s + ' ' for s in mstates if s.startswith(text)]
        return []

    # --- Other do_* and help_* methods from original Prompt ---
    def do_kulutus(self, arg_str):
        """Generates consumption for all APs/RPs based on prompted date/days."""
        args = arg_str.split()
        s_date, num_d = None, None
        if len(args) == 2:
            s_date, num_d = args[0], args[1]
        elif len(args) != 0:
            print(red + "Usage: kulutus [start_date num_days]" + reset)
            print(cyan + "If no arguments, will prompt for date and days." + reset)
            return

        # This command in original directly called luo_kulutus for ALL items.
        # It did not use the 'set' parameters from the prompt for apoint, etc.
        # It used dategen's internal prompting if date/days not given.
        print(cyan + "Starting batch generation for all Accounting and Exchange Points." + reset)
        self.generator._batch_generate_consumption(
            start_date_input=s_date,
            num_days_input=num_d
            # metering_state_code will be default '' (OK)
        )
        print(green + "Batch consumption generation finished." + reset)

    def help_kulutus(self):
        print("Syntax: kulutus [start_date_dd.mm.yyyy num_days]")
        print("-- Generates consumption data for ALL accounting and exchange points.")
        print("-- If start_date and num_days are not provided, you will be prompted for them.")
        print("-- This does not use 'set' parameters like specific apoint or metering_state.")

    # do_send is now more specific to the last generated single_kulutus XML
    def do_send(self, arg):
        """Sends the last generated XML file (from 'single_kulutus') to Datahub."""
        last_xml_path = self.generator.transient_data.get('last_generated_xml_path')

        if not last_xml_path:
            print(magenta + "No XML file has been generated yet in this session using 'single_kulutus'." + reset)
            print(magenta + "Please use 'single_kulutus' to generate data first." + reset)
            return

        if not self.apoint or not self.dso:
            print(magenta + "Accounting Point (apoint) and its DSO are not set." + reset)
            print(magenta + "Please use 'set apoint <id>' before sending." + reset)
            return

        xml_filename_only = os.path.basename(last_xml_path)

        # Confirm the file actually exists where req_utils expects it
        # req_utils.send_generic prepends its own 'xml/' path
        expected_path_for_req_utils = os.path.join("xml", xml_filename_only)
        if not os.path.exists(expected_path_for_req_utils):
            # This might happen if last_xml_path was absolute or not in the root 'xml/' dir.
            # For simplicity, we assume generator places it in 'xml/' relative to script root.
            print(red + f"Error: XML file '{xml_filename_only}' not found at expected location '{expected_path_for_req_utils}'." + reset)
            print(red + "Ensure it was generated into the correct directory by 'single_kulutus'." + reset)
            return

        print(cyan + f"Attempting to send: {xml_filename_only} (DSO context from set apoint: {self.dso})" + reset)

        try:
            # req_utils.send_generic determines the actual endpoint from fconfig based on
            # the DSO ID parsed from the XML content itself. The self.dso here is mostly for user context
            # and to ensure an AP was selected. The crucial part is that the XML file's content
            # has a PhysicalSenderEnergyParty ID that is correctly mapped in fconfig.DSO.
            from libs.req_utils import send_generic as req_utils_send_generic

            # The second argument to send_generic in req_utils is 'source_type' (e.g., 'DSO', 'DDQ')
            # For consumption data (E66), 'DSO' is the typical sender type.
            result = req_utils_send_generic(xml_filename_only, 'DSO')

            if result == 0: # Assuming 0 is success from req_utils.send_generic
                print(green + f"File {xml_filename_only} processed by req_utils. Check logs for Datahub response." + reset)
                # Original logic moved the file to DONE_ on success. req_utils handles this.
            else:
                print(red + f"File {xml_filename_only} processing by req_utils reported an issue. Check logs." + reset)

        except ImportError:
            print(red + "Error: Could not import 'send_generic' from libs.req_utils. Sending aborted." + reset)
        except Exception as e:
            print(red + f"An unexpected error occurred during send operation: {e}" + reset)

    def help_send(self):
        print("Syntax: send")
        print("-- Sends the XML file generated by the last 'single_kulutus' command.")
        print("-- Requires 'apoint' to be set to determine the context (though actual endpoint is from XML content via fconfig).")

    # --- Standard Cmd methods ---
    def emptyline(self):
        """Called when an empty line is entered. Does nothing."""
        pass

    def default(self, line):
        """Called on an input line when the command prefix is not recognized."""
        print(red + f"*** Unknown command: {line.strip()}" + reset)
        print(cyan + "Type 'help' for a list of available commands." + reset)

    def completenames(self, text, line, begidx, endidx):
        """Custom command name completion."""
        # This is a common way to get all do_* methods as completable commands
        # Original was: dotext = 'do_'+text; return [a[3:]+' ' for a in self.get_names() if a.startswith(dotext) and a not in self.__hidden_methods]
        # The self.__hidden_methods was ('do_EOF',). Let's adapt.
        # However, cmd.Cmd does this by default for methods starting with "do_".
        # We might only need to override if we want to exclude some 'do_' methods or add other completions.
        # For now, let's rely on default behavior or a simple version if needed.
        # The original code's completenames was slightly more complex to add a space and filter.
        
        # A simple approach to get all "do_" methods, strip "do_", and add a space
        method_names = [name[3:] for name in self.get_names() if name.startswith('do_') and name not in ['do_EOF']]
        if text:
            return [name + ' ' for name in method_names if name.startswith(text)]
        return [name + ' ' for name in method_names]

    def help_help(self):
        print(cyan + "Use 'help <command>' to get help on a specific command." + reset)
        print(cyan + "Available commands are listed when you type 'help' or '?'." + reset)

    def help_exit(self):
        print("Syntax: exit")
        print("-- Exits the interactive command prompt.")

    do_EOF = do_exit # Alias for Ctrl+D
    help_EOF = help_exit


def main_cli(argv):
    """Main command-line interface handler for kulugen."""
    cmd_opts_dict = {'interactive_mode': False}
    start_date_str = None
    num_days_str = None

    try:
        opts, args = getopt(argv, "hcs:d:", ["help", "interactive", "startdate=", "days="])
    except GetoptError as e:
        print(red + f"Argument parsing error: {e}" + reset, file=sys.stderr)
        print(cyan + "Usage: kulugen.py [-c] [-s <startdate>] [-d <days>] [-h]" + reset, file=sys.stderr)
        sys.exit(2)

    for opt, arg_val in opts:
        if opt in ("-h", "--help"):
            print(cyan + "Kulugen - Consumption Data Generator" + reset)
            print("Usage: kulugen.py [options]")
            print("Options:")
            print("  -c, --interactive : Run in interactive command-line mode.")
            print("  -s, --startdate dd.mm.yyyy : Specify start date for batch generation.")
            print("  -d, --days <number>        : Specify number of days for batch generation.")
            print("  -h, --help                 : Display this help message.")
            print("\nIf -s and -d are provided without -c, runs in batch mode.")
            print("If only -c is provided, runs in interactive mode.")
            print("If no arguments are provided, runs in default batch mode (prompts for dates).")
            sys.exit(0)
        elif opt in ("-c", "--interactive"):
            cmd_opts_dict['interactive_mode'] = True
        elif opt in ("-s", "--startdate"):
            start_date_str = arg_val
        elif opt in ("-d", "--days"):
            num_days_str = arg_val

    # Validate date and days if both provided for batch mode
    if start_date_str or num_days_str: # if either is set, both should be for non-interactive batch
        if not (start_date_str and num_days_str):
            print(red + "Error: Both start date (-s) and number of days (-d) must be provided for batch mode." + reset, file=sys.stderr)
            sys.exit(2)
        # Further validation (format, type) can be done here or in ConsumptionGenerator
        cmd_opts_dict['start_date_str'] = start_date_str
        cmd_opts_dict['num_days_str'] = num_days_str


    # Instantiate and run the generator
    try:
        generator = ConsumptionGenerator(cmd_args=cmd_opts_dict)
        generator.run()
    except ImportError as e:
        print(red + bold + f"Critical Import Error: {e}. Cannot continue." + reset, file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(red + bold + f"Critical File Not Found Error: {e}. Cannot continue." + reset, file=sys.stderr)
        sys.exit(1)
    except sqlite3.Error as e:
        print(red + bold + f"Database Error: {e}. Cannot continue." + reset, file=sys.stderr)
        sys.exit(1)
    except ValueError as e: # For config or parameter errors raised by the generator
        print(red + bold + f"Configuration or Value Error: {e}."+reset, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(red + bold + f"An unexpected error occurred: {e}" + reset, file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        main_cli(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n" + green + "Program cancelled by user (Ctrl+C)." + reset)
        sys.exit(0)
    except EOFError: # Should be caught by Cmd in interactive mode, but as a fallback
        print("\n" + green + "Input stream closed (EOF)." + reset)
        sys.exit(0)
