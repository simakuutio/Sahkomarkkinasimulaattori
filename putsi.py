#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import xml.etree.ElementTree as ET
import requests

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

class QueueProcessor:
    """
    Processes messages from a queue by peeking, saving, and dequeuing.
    """

    def __init__(self,
                 peek_template_path="libs/peek.xml",
                 dequeue_template_path="libs/dequeue_one.xml",
                 output_dir="peeks/"):
        """
        Initializes the QueueProcessor.

        Args:
            peek_template_path (str): Path to the XML template for peeking messages.
            dequeue_template_path (str): Path to the XML template for dequeuing messages.
            output_dir (str): Directory where peeked message XML files will be saved.
        """
        self.config = {}
        self.headers = {'content-type': 'text/xml;charset=UTF-8'} # From original soapreq/datareq
        self.certs = ("certs/cert.pem", "certs/key_nopass.pem") # Ensure these paths are correct

        self.peek_xml_template_path = peek_template_path
        self.dequeue_xml_template_path = dequeue_template_path
        self.peek_xml_content = ""  # Loaded by _load_peek_template

        self.output_dir = output_dir

        self.stats = {'OK': 0, 'FAIL': 0, 'OTHER': 0, 'processed_total': 0}

        # Stores details of the currently peeked message
        self.current_message_details = {'docref': None, 'process': None, 'status': None, 'raw_response': None}

        self._load_config()
        self._ensure_output_dir_exists()
        self._load_peek_template()

    def _load_config(self):
        """Loads configuration, specifically the putsiurl."""
        try:
            from libs.fconfig import putsiurl
            self.config['putsiurl'] = putsiurl
        except ImportError:
            print(f"{red}{bold}Error: libs.fconfig.py or 'putsiurl' variable missing. Cannot proceed.{reset}")
            raise # Critical configuration missing

    def _ensure_output_dir_exists(self):
        """Ensures the output directory for peeked messages exists."""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as e:
            print(f"{red}Error creating output directory {self.output_dir}: {e}{reset}")
            raise # Critical for saving messages

    def _load_peek_template(self):
        """Loads the content of the peek XML template file."""
        try:
            with open(self.peek_xml_template_path, 'r', encoding='utf-8') as f:
                self.peek_xml_content = f.read()
            if not self.peek_xml_content:
                raise ValueError(f"Peek template file '{self.peek_xml_template_path}' is empty.")
        except FileNotFoundError:
            print(f"{red}Error: Peek XML template file '{self.peek_xml_template_path}' not found.{reset}")
            raise # Critical for peeking
        except ValueError as e:
            print(f"{red}{e}{reset}")
            raise
        except IOError as e:
            print(f"{red}Error reading peek template file '{self.peek_xml_template_path}': {e}{reset}")
            raise

    def _http_post(self, url, data):
        """
        Performs an HTTP POST request.

        Args:
            url (str): The URL to post to.
            data (str): The XML data to post.

        Returns:
            requests.Response object if successful, None otherwise.
        """
        try:
            response = requests.post(url, data=data.encode('utf-8'), headers=self.headers, cert=self.certs, timeout=30) # Added timeout
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            return response
        except requests.exceptions.HTTPError as e_http:
            print(f"{red}HTTP Error: {e_http.response.status_code} for URL {url}. Response: {e_http.response.text[:200]}{reset}")
        except requests.exceptions.ConnectionError as e_conn:
            print(f"{red}Connection Error: {e_conn} for URL {url}{reset}")
        except requests.exceptions.Timeout as e_timeout:
            print(f"{red}Timeout Error for URL {url}: {e_timeout}{reset}")
        except requests.exceptions.RequestException as e_req:
            print(f"{red}Request Exception for URL {url}: {e_req}{reset}")
        return None

    def peek_message(self):
        """
        Peeks a message from the queue, parses details, and saves it.

        Returns:
            bool: True if a message was successfully peeked and processed, False otherwise.
        """
        self.current_message_details = {'docref': None, 'process': None, 'status': None, 'raw_response': None}

        if not self.peek_xml_content or not self.config.get('putsiurl'):
            print(f"{red}Error: Peek template or Putsi URL not loaded. Cannot peek.{reset}")
            return False

        print(f"{cyan}Peeking for new message...{reset}")
        response = self._http_post(self.config['putsiurl'], self.peek_xml_content)

        if response is None or not response.content:
            print(f"{yellow}Peek request failed or returned empty response.{reset}")
            return False

        raw_resp_str = response.content.decode("utf-8", errors='replace')
        self.current_message_details['raw_response'] = raw_resp_str

        # Regex patterns (from original putsi.py)
        # Docref may appear multiple times, but we are interested in the first one as the main document reference
        docref_matches = re.findall(r'(?<=urn2:Identification\>)(.*?)(?=\</urn2)', raw_resp_str) # urn2 might be specific, adjust if needed
        process_matches = re.findall(r'(?<=urn1:ProcessType\>)(.*?)(?=\</urn1)', raw_resp_str) # urn1 might be specific
        status_match = re.search('(?:BA01|BA02)', raw_resp_str) # BA01=OK, BA02=FAIL

        if not docref_matches:
            # This is the "normal" end condition: queue is empty
            print(f"{green}Queue seems to be empty or no message with DocumentReferenceNumber found.{reset}")
            return False

        self.current_message_details['docref'] = docref_matches[0] # Take the first docref

        process_type = process_matches[0] if process_matches else "UnknownProcess"
        self.current_message_details['process'] = process_type

        parsed_status = "None"
        if status_match:
            parsed_status = status_match.group(0)
            if parsed_status == "BA01": self.stats['OK'] += 1
            elif parsed_status == "BA02": self.stats['FAIL'] += 1
        else:
            self.stats['OTHER'] += 1
        self.current_message_details['status'] = parsed_status

        # Filename construction
        # Replace characters that are problematic in filenames
        safe_process = re.sub(r'[<>:"/\\|?*]', '_', self.current_message_details['process'])
        safe_docref = re.sub(r'[<>:"/\\|?*]', '_', self.current_message_details['docref'])
        save_fn = f"{parsed_status}_{safe_process}_{safe_docref}.xml"
        output_path = os.path.join(self.output_dir, save_fn)

        try:
            with open(output_path, 'w', encoding='utf-8') as f_out:
                f_out.write(raw_resp_str)
            print(f"Saved peeked message to: {output_path}")
        except IOError as e:
            print(f"{red}Error writing peeked message to file {output_path}: {e}{reset}")
            # Continue to dequeue even if saving fails, as message is already peeked.

        return True # Message peeked (and saved if possible)

    def dequeue_current_message(self):
        """
        Dequeues the message currently stored in self.current_message_details.

        Returns:
            bool: True if dequeue was successful, False otherwise.
        """
        docref_to_dequeue = self.current_message_details.get('docref')
        if not docref_to_dequeue:
            print(f"{red}Error: No current message (docref) to dequeue. Peek first.{reset}")
            return False

        if not self.config.get('putsiurl'):
            print(f"{red}Error: Putsi URL not configured. Cannot dequeue.{reset}")
            return False

        try:
            tree = ET.parse(self.dequeue_xml_template_path)
            # Namespace for CMS messages (verify from dequeue_one.xml)
            # Original: ns_cms = './/{urn:cms:b2b:v01}'
            # For ET.find, the path should be relative to the element it's called on.
            # If DocumentReferenceNumber is a direct child of root with that namespace:
            # Or, if it can be anywhere: ".//{urn:cms:b2b:v01}DocumentReferenceNumber"
            doc_ref_elem = tree.find(".//{urn:cms:b2b:v01}DocumentReferenceNumber")

            if doc_ref_elem is None:
                print(f"{red}Error: Cannot find 'DocumentReferenceNumber' in dequeue template '{self.dequeue_xml_template_path}'.{reset}")
                return False

            doc_ref_elem.text = docref_to_dequeue

            # Serialize the modified XML to a string to send
            # ET.tostring() returns bytes, so decode to string
            dequeue_xml_data = ET.tostring(tree.getroot(), encoding='unicode')

        except FileNotFoundError:
            print(f"{red}Error: Dequeue XML template '{self.dequeue_xml_template_path}' not found.{reset}")
            return False
        except ET.ParseError as e:
            print(f"{red}Error parsing dequeue template '{self.dequeue_xml_template_path}': {e}{reset}")
            return False
        except Exception as e: # Catch other errors during XML prep
            print(f"{red}Error preparing dequeue XML: {e}{reset}")
            return False

        print(f"{cyan}Dequeuing message with DocRef: {docref_to_dequeue}...{reset}")
        response = self._http_post(self.config['putsiurl'], dequeue_xml_data)

        if response and response.status_code == 200: # Check for successful HTTP status
             # Optionally, check response content for confirmation if API provides one
            print(f"{green}Message {docref_to_dequeue} dequeued successfully (HTTP 200).{reset}")
            return True
        else:
            print(f"{red}Dequeue failed for {docref_to_dequeue}. HTTP status: {response.status_code if response else 'N/A'}{reset}")
            return False

    def process_queue_loop(self):
        """
        Continuously peeks and dequeues messages until the queue is empty or an error occurs.
        """
        print(f"{cyan}Starting queue processing loop...{reset}")
        while self.peek_message(): # peek_message returns True if a message was found and processed
            if self.current_message_details.get('docref'): # Ensure there's a docref to dequeue
                if not self.dequeue_current_message():
                    print(f"{red}Failed to dequeue message {self.current_message_details.get('docref')}. Stopping to avoid loop.{reset}")
                    break # Stop if dequeue fails to prevent potential infinite loop on same message
                self.stats['processed_total'] += 1
            else: # Should not happen if peek_message returned True, but as a safeguard
                print(f"{yellow}Peek reported success but no docref found. Stopping.{reset}")
                break
            print("-" * 30) # Separator

        self.print_summary()

    def print_summary(self):
        """Prints a summary of the processed messages."""
        print(f"\n{cyan}--- Processing Summary ---{reset}")
        print(f"Total messages processed: {self.stats['processed_total']}")
        print(f"  {green}OK (BA01) status: {self.stats['OK']}{reset}")
        print(f"  {red}FAIL (BA02) status: {self.stats['FAIL']}{reset}")
        print(f"  {yellow}OTHER status: {self.stats['OTHER']}{reset}")
        print(f"{cyan}--------------------------{reset}")


if __name__ == "__main__":
    print(f"{cyan}--- Putsi Queue Processor ---{reset}")
    try:
        processor = QueueProcessor()
        processor.process_queue_loop()
    except ImportError:
        # Error already printed by _load_config, main block just ensures clean exit
        print(f"{red}{bold}Critical configuration import error. Putsi cannot run.{reset}")
        sys.exit(1)
    except FileNotFoundError:
        # Error already printed by _load_peek_template or _ensure_output_dir_exists
        print(f"{red}{bold}Essential file/directory missing. Putsi cannot run.{reset}")
        sys.exit(1)
    except requests.exceptions.RequestException as e: # Catch any critical request errors not handled by _http_post
        print(f"{red}{bold}A critical network request failed during startup or core operation: {e}{reset}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{yellow}Processing interrupted by user (Ctrl+C).{reset}")
    except Exception as e:
        import traceback
        print(f"{red}{bold}An unexpected critical error occurred:\n{e}\n{traceback.format_exc()}{reset}")
        sys.exit(1)
    finally:
        print(f"{cyan}--- Putsi processing finished ---{reset}")

```
