#display.py
# Description:
# This file, display.py, is responsible for managing the e-ink display of the Bjorn project, updating it with relevant data and statuses.
# It initializes the display, manages multiple threads for updating shared data and vulnerability counts, and handles the rendering of information
# and images on the display.
#
# Key functionalities include:
# - Initializing the e-ink display (EPD) and handling any errors during initialization.
# - Creating and managing threads to periodically update shared data and vulnerability counts.
# - Rendering various statistics, status icons, and images on the e-ink display.
# - Handling updates to shared data from various sources, including CSV files and system commands.
# - Checking and displaying the status of Bluetooth, Wi-Fi, PAN, and USB connections.
# - Providing methods to update the display with comments from an AI (Commentaireia) and generating images dynamically.

import threading
import time
import os
import pandas as pd
import signal
import glob
import logging
import random
import sys
from PIL import Image, ImageDraw
from init_shared import shared_data  
from comment import Commentaireia
from display_layout import DisplayLayout
from logger import Logger
import subprocess  

logger = Logger(name="display.py", level=logging.DEBUG)

class Display:
    def __init__(self, shared_data):
        """Initialize the display and start the main image and shared data update threads."""
        self.shared_data = shared_data
        self.config = self.shared_data.config
        self.shared_data.bjornstatustext2 = "Awakening..."
        self.commentaire_ia = Commentaireia()
        self.semaphore = threading.Semaphore(10)
        self.screen_reversed = self.shared_data.screen_reversed
        self.web_screen_reversed = self.shared_data.web_screen_reversed

        # PORT-3: data-driven layout (replaces hardcoded coordinates in run()).
        self.layout = DisplayLayout(self.shared_data)

        try:
            self.epd_helper = self.shared_data.epd_helper
            # PORT-11: in headless mode epd_helper is None — skip hardware
            # init, the render→screen.png path still feeds the web UI.
            if self.epd_helper:
                self.epd_helper.init_partial_update()
            logger.info("Display initialization complete.")
        except Exception as e:
            logger.error(f"Error during display initialization: {e}")
            raise

        self.main_image_thread = threading.Thread(target=self.update_main_image)
        self.main_image_thread.daemon = True
        self.main_image_thread.start()

        self.update_shared_data_thread = threading.Thread(target=self.schedule_update_shared_data)
        self.update_shared_data_thread.daemon = True
        self.update_shared_data_thread.start()

        self.update_vuln_count_thread = threading.Thread(target=self.schedule_update_vuln_count)
        self.update_vuln_count_thread.daemon = True
        self.update_vuln_count_thread.start()

        self.scale_factor_x = self.shared_data.scale_factor_x
        self.scale_factor_y = self.shared_data.scale_factor_y

    def schedule_update_shared_data(self):
        """Periodically update the shared data with the latest system information."""
        while not self.shared_data.display_should_exit:
            self.update_shared_data()
            time.sleep(25)

    def schedule_update_vuln_count(self):
        """Periodically update the vulnerability count on the display."""
        while not self.shared_data.display_should_exit:
            self.update_vuln_count()
            time.sleep(300)

    def update_main_image(self):
        """Update the main image on the display with the latest immagegen data."""
        while not self.shared_data.display_should_exit:
            try:
                self.shared_data.update_image_randomizer()
                if self.shared_data.imagegen:
                    self.main_image = self.shared_data.imagegen
                else:
                    logger.error("No image generated for current status.")
                time.sleep(random.uniform(self.shared_data.image_display_delaymin, self.shared_data.image_display_delaymax))
            except Exception as e:
                logger.error(f"An error occurred in update_main_image: {e}")

    def get_open_files(self):
        """Get the number of open FD files on the system."""
        try:
            open_files = len(glob.glob('/proc/*/fd/*'))
            logger.debug(f"FD : {open_files}")
            return open_files
        except Exception as e:
            logger.error(f"Error getting open files: {e}")
            return None
        
    def update_vuln_count(self):
        """Update the vulnerability count on the display."""
        with self.semaphore:
            try:
                if not os.path.exists(self.shared_data.vuln_summary_file):
                    df = pd.DataFrame(columns=["IP", "Hostname", "MAC Address", "Port", "Vulnerabilities"])
                    df.to_csv(self.shared_data.vuln_summary_file, index=False)
                    self.shared_data.vulnnbr = 0
                    logger.info("Vulnerability summary file created.")
                else:
                    if os.path.exists(self.shared_data.netkbfile):
                        # DSP-2: pd.read_csv accepts a path directly; the
                        # open() wrapper is redundant.
                        netkb_df = pd.read_csv(self.shared_data.netkbfile)
                        alive_macs = set(netkb_df[(netkb_df["Alive"] == 1) & (netkb_df["MAC Address"] != "STANDALONE")]["MAC Address"])
                    else:
                        alive_macs = set()

                    # DSP-2: drop the unnecessary open() around read_csv.
                    df = pd.read_csv(self.shared_data.vuln_summary_file)
                    all_vulnerabilities = set()

                    # DSP-4: vectorise instead of the slow row-iteration
                    # pattern pandas docs warn against. Filter the
                    # dataframe once, drop NaN, then split + unionise.
                    alive_df = df[df["MAC Address"].isin(alive_macs)
                                  & (df["MAC Address"] != "STANDALONE")]
                    vuln_series = alive_df["Vulnerabilities"].dropna().astype(str)
                    if not vuln_series.empty:
                        # Join all rows, split on separator, deduplicate via set.
                        joined = "; ".join(vuln_series.tolist())
                        all_vulnerabilities = set(joined.split("; "))

                    self.shared_data.vulnnbr = len(all_vulnerabilities)
                    logger.debug(f"Updated vulnerabilities count: {self.shared_data.vulnnbr}")

                    if os.path.exists(self.shared_data.livestatusfile):
                        # DSP-1: previously to_csv() was called WHILE the
                        # same file was open via `with open('r+')`, racing
                        # and truncating under the live handle. Pass the
                        # path directly to both read_csv and to_csv.
                        livestatus_df = pd.read_csv(self.shared_data.livestatusfile)
                        livestatus_df.loc[0, 'Vulnerabilities Count'] = self.shared_data.vulnnbr
                        livestatus_df.to_csv(self.shared_data.livestatusfile, index=False)
                        logger.debug(f"Updated livestatusfile with vulnerability count: {self.shared_data.vulnnbr}")
                    else:
                        logger.error(f"Livestatusfile {self.shared_data.livestatusfile} does not exist.")
            except Exception as e:
                logger.error(f"An error occurred in update_vuln_count: {e}")

    def update_shared_data(self):
        """Update the shared data with the latest system information."""
        with self.semaphore:
            try:
                # DSP-2: pd.read_csv accepts a path directly.
                livestatus_df = pd.read_csv(self.shared_data.livestatusfile)
                self.shared_data.portnbr = livestatus_df['Total Open Ports'].iloc[0]
                self.shared_data.targetnbr = livestatus_df['Alive Hosts Count'].iloc[0]
                self.shared_data.networkkbnbr = livestatus_df['All Known Hosts Count'].iloc[0]
                self.shared_data.vulnnbr = livestatus_df['Vulnerabilities Count'].iloc[0]

                crackedpw_files = glob.glob(f"{self.shared_data.crackedpwddir}/*.csv")

                total_passwords = 0
                for file in crackedpw_files:
                    total_passwords += len(pd.read_csv(file, usecols=[0]))

                self.shared_data.crednbr = total_passwords

                total_data = sum([len(files) for r, d, files in os.walk(self.shared_data.datastolendir)])
                self.shared_data.datanbr = total_data

                total_zombies = sum([len(files) for r, d, files in os.walk(self.shared_data.zombiesdir)])
                self.shared_data.zombiesnbr = total_zombies
                total_attacks = sum([len(files) for r, d, files in os.walk(self.shared_data.actions_dir) if not r.endswith("__pycache__")]) - 2

                self.shared_data.attacksnbr = total_attacks

                self.shared_data.update_stats()
                self.shared_data.manual_mode = self.is_manual_mode()
                if self.shared_data.manual_mode:
                    self.manual_mode_txt = "M"
                else:
                    self.manual_mode_txt = "A"
                self.shared_data.wifi_connected = self.is_wifi_connected()
                self.shared_data.usb_active = self.is_usb_connected()
                self.get_open_files()

            except (FileNotFoundError, pd.errors.EmptyDataError) as e:
                logger.error(f"Error: {e}")
            except Exception as e:
                logger.error(f"Error updating shared data: {e}")

    def display_comment(self, status):
        """Display the comment based on the status of the BjornOrch."""
        comment = self.commentaire_ia.get_commentaire(status)
        if comment:
            self.shared_data.bjornsay = comment
            self.shared_data.bjornstatustext = self.shared_data.bjornorch_status
        else:
            pass

    # # # def is_bluetooth_connected(self):
    # # #     """
    # # #     Check if any device is connected to the Bluetooth (pan0) interface by checking the output of 'ip neigh show dev pan0'.
    # # #     """
    # # #     try:
    # # #         result = subprocess.Popen(['ip', 'neigh', 'show', 'dev', 'pan0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # # #         output, error = result.communicate()
    # # #         if result.returncode != 0:
    # # #             logger.error(f"Error executing 'ip neigh show dev pan0': {error}")
    # # #             return False
    # # #         return bool(output.strip())
    # # #     except Exception as e:
    # # #         logger.error(f"Error checking Bluetooth connection status: {e}")
    # # #         return False

    def is_wifi_connected(self):
        """Check if WiFi is connected by checking the current SSID."""
        try:
            result = subprocess.Popen(['iwgetid', '-r'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            ssid, error = result.communicate()
            if result.returncode != 0:
                logger.error(f"Error executing 'iwgetid -r': {error}")
                return False
            return bool(ssid.strip())
        except Exception as e:
            logger.error(f"Error checking WiFi status: {e}")
            return False

    def is_manual_mode(self):
        """Check if the BjornOrch is in manual mode."""
        return self.shared_data.manual_mode

    def is_interface_connected(self, interface):
        """Check if any device is connected to the specified interface."""
        try:
            result = subprocess.Popen(['ip', 'neigh', 'show', 'dev', interface], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output, error = result.communicate()
            if result.returncode != 0:
                logger.error(f"Error executing 'ip neigh show dev {interface}': {error}")
                return False
            return bool(output.strip())
        except Exception as e:
            logger.error(f"Error checking connection status on {interface}: {e}")
            return False

    def is_usb_connected(self):
        """Check if any device is connected to the USB interface."""
        try:
            result = subprocess.Popen(['ip', 'neigh', 'show', 'dev', 'usb0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output, error = result.communicate()
            if result.returncode != 0:
                logger.error(f"Error executing 'ip neigh show dev usb0': {error}")
                return False
            return bool(output.strip())
        except Exception as e:
            logger.error(f"Error checking USB connection status: {e}")
            return False

    def run(self):
        """Main loop for updating the EPD display with shared data."""
        self.manual_mode_txt = ""
        while not self.shared_data.display_should_exit:
            try:
                # PORT-11: hardware push only when an EPD is present.
                if self.epd_helper:
                    self.epd_helper.init_partial_update()
                self.display_comment(self.shared_data.bjornorch_status)
                image = Image.new('1', (self.shared_data.width, self.shared_data.height))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, self.shared_data.width, self.shared_data.height), fill=255)
                # PORT-3: all coordinates come from self.layout (data-driven).
                # Values are identical to the pre-PORT-3 literals — verify with
                # a side-by-side screenshot on the HW session.
                def _pos(el):
                    return (int(el["x"] * self.scale_factor_x),
                            int(el["y"] * self.scale_factor_y))

                draw.text(_pos(self.layout.get("title")), "BJORN", font=self.shared_data.font_viking, fill=0)
                draw.text(_pos(self.layout.get("manual_mode")), self.manual_mode_txt, font=self.shared_data.font_arial14, fill=0)

                if self.shared_data.wifi_connected:
                    image.paste(self.shared_data.wifi, _pos(self.layout.get("wifi_icon")))
                # # # if self.shared_data.bluetooth_active:
                # # #     image.paste(self.shared_data.bluetooth, (int(23 * self.scale_factor_x), int(4 * self.scale_factor_y)))
                if self.shared_data.pan_connected:
                    image.paste(self.shared_data.connected, _pos(self.layout.get("pan_icon")))
                if self.shared_data.usb_active:
                    image.paste(self.shared_data.usb, _pos(self.layout.get("usb_icon")))

                # Stats row: iterate layout stats, bind icon/counter by attr name.
                for stat in self.layout.stats():
                    img = getattr(self.shared_data, stat["stat_attr"], None)
                    count = getattr(self.shared_data, stat["count_attr"], "")
                    if img is None:
                        continue
                    image.paste(img, _pos(stat["img"]))
                    draw.text(_pos(stat["text"]), str(count), font=self.shared_data.font_arial9, fill=0)

                self.shared_data.update_bjornstatus()
                image.paste(self.shared_data.bjornstatusimage, _pos(self.layout.get("status_image")))
                draw.text(_pos(self.layout.get("status_line1")), self.shared_data.bjornstatustext, font=self.shared_data.font_arial9, fill=0)
                draw.text(_pos(self.layout.get("status_line2")), self.shared_data.bjornstatustext2, font=self.shared_data.font_arial9, fill=0)

                # Frise position is EPD-type-dependent in the layout.
                frise = self.layout.frise()
                image.paste(self.shared_data.frise, _pos(frise))

                border = self.layout.get("border")
                draw.rectangle((int(border["x0"] * self.scale_factor_x),
                                int(border["y0"] * self.scale_factor_y),
                                self.shared_data.width - 1, self.shared_data.height - 1), outline=0)
                for line_key in ("line_top", "line_mid", "line_lower"):
                    ly = int(self.layout.get(line_key, "y") * self.scale_factor_y)
                    draw.line((1, ly, self.shared_data.width - 1, ly), fill=0)

                lines = self.shared_data.wrap_text(self.shared_data.bjornsay, self.shared_data.font_arialbold, self.shared_data.width - 4)
                comment = self.layout.get("comment_text")
                y_text = int(comment["y_start"] * self.scale_factor_y)

                if self.main_image is not None:
                    image.paste(self.main_image, (self.shared_data.x_center1, self.shared_data.y_bottom1))
                else:
                    logger.error("Main image not found in shared_data.")

                for line in lines:
                    draw.text((int(comment["x"] * self.scale_factor_x), y_text), line, font=self.shared_data.font_arialbold, fill=0)
                    y_text += (self.shared_data.font_arialbold.getbbox(line)[3] - self.shared_data.font_arialbold.getbbox(line)[1]) + 3

                if self.screen_reversed:
                    # DSP-3: the legacy module-level transpose constant is
                    # deprecated since Pillow 9.1. The enum form is required
                    # on Pillow 12+.
                    image = image.transpose(Image.Transpose.ROTATE_180)

                # PORT-11: push to hardware only when an EPD is attached.
                # The screen.png write below always runs so the web UI keeps
                # updating in headless mode.
                if self.epd_helper:
                    self.epd_helper.display_partial(image)
                    self.epd_helper.display_partial(image)

                if self.web_screen_reversed:
                    image = image.transpose(Image.Transpose.ROTATE_180)
                with open(os.path.join(self.shared_data.webdir, "screen.png"), 'wb') as img_file:
                    image.save(img_file)
                    img_file.flush()
                    os.fsync(img_file.fileno())
                
                time.sleep(self.shared_data.screen_delay)
            except Exception as e:
                logger.error(f"An error occurred: {e}")

def handle_exit_display(signum, frame, display_thread):
    """Tear down the EPD hardware on exit.

    ARCH-2: the previous version of this helper blocked on the display
    thread and then terminated the process via the stdlib exit function.
    The termination call raised SystemExit at the end of this helper,
    which made any code in callers AFTER the call to this helper
    unreachable (the bjorn/web thread joins in Bjorn.handle_exit were
    dead). The thread-wait was also redundant with the caller's wait.
    Both removed; this helper now ONLY tears down the EPD. Flag-based
    cleanup happens in the main loop / process exit.
    """
    global should_exit
    shared_data.display_should_exit = True
    logger.info("Exit signal received. Waiting for the main loop to finish...")
    try:
        # PORT-2: EPDManager exposes sleep(); the old code referenced a
        # non-existent main_loop.epd and silently no-op'd. Headless mode
        # (PORT-11) has no epd_helper at all.
        if main_loop and getattr(main_loop, "epd_helper", None):
            main_loop.epd_helper.sleep()
    except Exception as e:
        logger.error(f"Error while closing the display: {e}")

# Declare main_loop globally
main_loop = None

if __name__ == "__main__":
    try:
        logger.info("Starting main loop...")
        main_loop = Display(shared_data)
        display_thread = threading.Thread(target=main_loop.run)
        display_thread.start()
        logger.info("Main loop started.")
        
        signal.signal(signal.SIGINT, lambda signum, frame: handle_exit_display(signum, frame, display_thread))
        signal.signal(signal.SIGTERM, lambda signum, frame: handle_exit_display(signum, frame, display_thread))
    except Exception as e:
        logger.error(f"An exception occurred during program execution: {e}")
        handle_exit_display(signal.SIGINT, None, display_thread)
        sys.exit(1)