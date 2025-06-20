#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
This module provides shared utility functions for making HTTP requests
and handling responses, primarily for datareq.py and soapreq.py.
It centralizes request logic, error handling, and logging.
"""

import os
import re
import sys
import requests # For requests.post and requests.exceptions.RequestException
import shutil # For shutil.move
from timeit import default_timer as timer # For timing requests
from datetime import timedelta # For timing requests
import time # For sleep in thread_loop, if that's also moved or used by send_generic

# Attempt to import from libs.fconfig, handle if not found
try:
    from libs.fconfig import DSO, DDQ, url
except ImportError:
    print('Error: fconfig.py missing from libs directory. req_utils.py cannot function.')
    # Depending on desired behavior, could exit or let parts of the module fail if used.
    # For now, print error. Callers will likely fail if these are None.
    DSO, DDQ, url = None, None, None

DEBUG = False
headers = {'content-type': 'text/xml'}
xml_path = 'xml/' # Assuming XML files are in an 'xml' subdirectory relative to where the main scripts are run.

def dprint(*s):
    """Prints debug messages if DEBUG is True."""
    if DEBUG:
        print(s)

def Printer(data):
    """
    Prints data to stdout on one line, primarily for progress updates.
    Output is conditional on the DEBUG flag.
    """
    if DEBUG: # Matching original behavior where Printer output was conditional on DEBUG
        sys.stdout.write("\r\x1b[K"+data.__str__())
        sys.stdout.flush()

def read_file_to_list(input_file):
    """
    Reads all lines from a given file and returns them as a list of strings.
    Strips whitespace from each line.
    """
    dprint(f'read_file_to_list({input_file})')
    lista = []
    try:
        with open(input_file, 'r') as f:
            for line in f:
                lista.append(line.strip())
    except FileNotFoundError:
        dprint(f"Error: File not found - {input_file} in read_file_to_list.")
        # Depending on how critical these files are, might raise or return empty
    return lista

def find_error(error_code):
    """
    Looks up a human-readable error description based on an error code.
    Error codes and strings are read from 'Error_code.txt' and 'Error_string.txt'.
    """
    dprint(f'find_error({error_code})')
    # Construct paths relative to this file's location (libs directory)
    base_dir = os.path.dirname(__file__)
    error_codes_path = os.path.join(base_dir, 'Error_code.txt')
    error_strings_path = os.path.join(base_dir, 'Error_string.txt')

    error_codes = read_file_to_list(error_codes_path)
    error_strings = read_file_to_list(error_strings_path)

    if not error_codes or not error_strings:
        return f"Unknown error code {error_code} (Error definition files missing or empty from {base_dir})"

    try:
        virhe_idx = error_codes.index(error_code) # Find index of the error code
        return error_strings[virhe_idx] # Return corresponding description
    except ValueError: # Error code not found in list
        return f"Unknown error code {error_code} (Not found in {error_codes_path})"
    except IndexError: # Error code found, but no matching description
        return f"Error code {error_code} found, but no corresponding string in {error_strings_path}"


def parse_for_uri(xml_content):
    """
    Parses XML content to extract an organization ID using regex.
    The ID is typically found within an <ns3:Identification> tag
    with a specific schemeAgencyIdentifier.
    """
    dprint('parse_for_uri(xml_content)')
    # Regex looks for content within <ns3:Identification> where schemeAgencyIdentifier="9"
    gen_id = re.search(r'(?<=schemeAgencyIdentifier\=\"9\"\>)(.*)(?=\<\/ns3:Identification)', xml_content)
    try:
        return gen_id.group(1) # Return the captured group (the organization ID)
    except AttributeError: # .group(1) fails if regex does not match
        print("Error: Could not parse organization ID from XML content. Regex did not match.")
        return None

def uri_gen(org_id, mode):
    """
    Generates a URI component based on the organization ID and mode (DSO or DDQ).
    This component is specific to the organization and is appended to the base URL.
    """
    dprint(f'uri_gen({org_id}, {mode})')
    if DSO is None or DDQ is None: # Check if fconfig was loaded correctly
        print("Error: DSO or DDQ is not configured in fconfig (uri_gen).")
        return None
    if mode == 'DSO':
        return DSO.get(org_id) # Use .get for safer dictionary access
    else: # Assuming 'DDQ' for other modes
        return DDQ.get(org_id) # Use .get for safer dictionary access

def gen_url(mode, xml_content):
    """
    Constructs the full request URL by parsing the organization ID from XML,
    generating the organization-specific URI part, and appending it to the base URL.
    """
    dprint(f'gen_url({mode}, xml_content)')
    if url is None: # Check if fconfig was loaded correctly
        print("Error: 'url' is not configured in fconfig (gen_url).")
        return None

    org_id = parse_for_uri(xml_content)
    if org_id is None:
        # Error already printed by parse_for_uri
        print("Error: Cannot generate URL due to parsing failure for XML (org_id was None).")
        return None

    org_uri_part = uri_gen(org_id, mode)
    if org_uri_part is None:
        # Error might be printed by uri_gen if DSO/DDQ missing, or here if org_id not in them
        print(f"Error: Could not find URI for org_id '{org_id}' in mode '{mode}'. Check fconfig.py.")
        return None

    return url + org_uri_part


def send_generic(source_filename, source_type):
    """
    Sends an XML file to a specified endpoint and handles the response.

    Args:
        source_filename (str): The name of the XML file (located in `xml_path`).
        source_type (str): The type of the source, typically 'DSO' or 'DDQ',
                           which determines the endpoint configuration.

    Returns:
        int: 0 for success, 1 for failure.

    This function reads an XML file, generates the target URL,
    posts the XML content, and then processes the response.
    It logs request and response details to files in the 'log' directory
    and prints progress and error messages to stdout.
    The specifics of response validation (e.g., checking for "BA01")
    are currently based on the requirements of soapreq.py.
    """
    dprint(f'send_generic({source_filename}, {source_type})')

    full_xml_path = os.path.join(xml_path, source_filename)
    # log_dir should ideally be configurable or passed, but using 'log' as per original scripts
    log_dir = 'log'

    # Ensure log directory exists
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except OSError as e:
            print(f"Error creating log directory {log_dir}: {e}")
            return 1 # Cannot proceed without logging

    # Read source XML file
    try:
        with open(full_xml_path, 'r') as source_xml_file:
            input_xml = source_xml_file.read()
    except FileNotFoundError:
        print(f"Error: Source XML file not found: {full_xml_path}")
        return 1
    except IOError as e:
        print(f"Error reading source XML file {full_xml_path}: {e}")
        return 1

    if DEBUG: start_time = timer()
    Printer(f'--> Sending {source_filename}') # Show progress

    # Generate the request URL
    req_url = gen_url(source_type, input_xml)
    if req_url is None:
        # Error messages are printed by gen_url or its sub-functions
        print(f"Skipping file {source_filename} due to URL generation error.")
        return 1

    try:
        # Make the POST request
        k_response = requests.post(req_url, data=input_xml, headers=headers, cert=("certs/cert.pem", "certs/key_nopass.pem"), timeout=30)

        if DEBUG:
            end_time = timer()
            time_delta = str(timedelta(seconds=end_time - start_time))
            print(f' Process time for {source_filename} : {time_delta.split(".")[0][2:]}') # [2:] to remove "0:" from "0:00:0S"

        # Decode response content, replacing errors if any
        response_content = k_response.content.decode("utf-8", errors="replace")

        # Log the response
        log_file_path = os.path.join(log_dir, 'resp_' + source_filename)
        try:
            with open(log_file_path, 'w') as db_log:
                db_log.write(response_content)
        except IOError as e:
            print(f"Warning: Error writing to log file {log_file_path}: {e}")
            # Continue processing even if log writing fails, but notify user.

        # --- Response Content Checking (currently based on soapreq.py logic) ---
        if "BA01" not in response_content: # "BA01" is a success indicator for soapreq.py
            fail_log_path = os.path.join(log_dir, 'FAIL_resp_' + source_filename)
            try:
                if os.path.exists(log_file_path): # If original log was written
                    shutil.move(log_file_path, fail_log_path)
                else: # If original log failed, write a new fail log
                    with open(fail_log_path, 'w') as db_fail_log:
                        db_fail_log.write(response_content + "\n\nFailure: BA01 not in response.")
            except Exception as e_move: # Catch errors during move/write of fail log
                print(f"Warning: Error handling fail log for {fail_log_path}: {e_move}")

            # Try to find a specific error code in the response
            reason_match = re.search(r'(?<=ErrorCode\>)(.*)(?=\<\/urn:ErrorCode)', response_content)
            if reason_match:
                error_message = find_error(reason_match.group(0))
                print(f"\nERROR: Sending {source_filename} failed: {error_message}")
            else:
                # This is the part that differs from datareq.py's original check
                # (which looked for "DocumentReferenceNumber").
                print(f'Error: Problem with response error parsing for {source_filename}, BA01 not found and no ErrorCode tag.')
            return 1 # Indicate failure
        elif "Unavailable" in response_content: # Check for service unavailability
            print(f'\nDatahub backend not available for {source_filename}, please try later again!')
            print('Possible reason: blocked by firewall')
            fail_log_path = os.path.join(log_dir, 'FAIL_resp_' + source_filename)
            if os.path.exists(log_file_path): shutil.move(log_file_path, fail_log_path) # Also log this as failure
            return 1 # Indicate failure
        else:
            # Request was successful
            Printer(f"*** {source_filename} sent succesfully.")
            done_xml_path = os.path.join(xml_path, 'DONE_' + source_filename)
            try:
                # Ensure source_xml_file is closed by 'with open' before moving.
                shutil.move(full_xml_path, done_xml_path)
            except Exception as e_move_xml:
                 print(f"Warning: Error moving original XML {full_xml_path} to {done_xml_path}: {e_move_xml}")
                 # Decide if this is a failure of send_generic or just a cleanup issue.
                 # For now, consider the send successful if response was OK.
            return 0 # Indicate success

    except requests.exceptions.RequestException as e: # Handle network/request-level errors
        print(f"\nERROR: Request failed for {source_filename}: {e}")
        fail_log_path = os.path.join(log_dir, 'FAIL_resp_' + source_filename)
        try: # Attempt to log the exception
            with open(fail_log_path, 'w') as db_fail_log:
                db_fail_log.write(f"RequestException: {e}\nURL: {req_url}")
        except IOError as ioe:
            print(f"Warning: Could not write to fail log {fail_log_path}: {ioe}")
        return 1 # Indicate failure
    except Exception as e_generic: # Catch any other unexpected errors
        print(f"\nUNEXPECTED ERROR during send_generic for {source_filename}: {e_generic}")
        # Attempt to log the generic error as well
        fail_log_path = os.path.join(log_dir, 'FAIL_resp_' + source_filename)
        try:
            with open(fail_log_path, 'w') as db_fail_log:
                db_fail_log.write(f"Unexpected Exception: {e_generic}\nURL: {req_url}")
        except IOError as ioe:
            print(f"Warning: Could not write to fail log {fail_log_path}: {ioe}")
        return 1 # Indicate failure

# Example for future extension if specific response checks are needed:
# def send_generic_datareq_check(response_content, source_filename, log_file_path, log_dir):
#    """Specific response check for datareq.py logic."""
#    if "DocumentReferenceNumber" not in response_content:
#        print(f'Error: Problem with response error parsing for {source_filename}, "DocumentReferenceNumber" not found.')
#        fail_log_path = os.path.join(log_dir, 'FAIL_resp_' + source_filename)
#        if os.path.exists(log_file_path): shutil.move(log_file_path, fail_log_path)
#        return 1 # Failure
#    return 0 # Success
