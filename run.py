import os
import platform
import subprocess
import requests
import tarfile
import zipfile
import shutil
import json
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit, QPushButton,
    QLabel, QProgressBar, QFileDialog, QTextEdit, QListWidget
)
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl

CONFIG_FILE = './config.json'

# Thread for running SteamCMD
class DownloadThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)

    def __init__(self, game_id, item_id, download_path, steamcmd_path):
        super().__init__()
        self.game_id = game_id
        self.item_id = item_id
        self.download_path = download_path
        self.steamcmd_path = steamcmd_path

    def run(self):
        try:
            # SteamCMD command
            cmd = [
                self.steamcmd_path,
                "+force_install_dir", self.download_path,
                "+login", "anonymous",
                "+workshop_download_item", self.game_id, self.item_id,
                "+quit"
            ]
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.download_path
            )
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                self.log.emit(line.decode("utf-8"))
                self.progress.emit(50)  # Example progress update
            process.wait()
            self.progress.emit(100)  # Mark as complete
        except Exception as e:
            self.log.emit(f"Error: {str(e)}")

# Main Application
class SteamWorkshopDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.download_queue = []

    def initUI(self):
        self.setWindowTitle("Brotato Steam Workshop Downloader")
        self.resize(800, 600)
        self.layout = QVBoxLayout()

        # Create a horizontal layout for the main and secondary output logs
        self.logs_layout = QHBoxLayout()

        # Left Output Log (main log)
        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)
        self.logs_layout.addWidget(self.log_output)

        # Right Output Log (steamcmd output log)
        self.steamcmd_log_output = QTextEdit(self)
        self.steamcmd_log_output.setReadOnly(True)
        self.logs_layout.addWidget(self.steamcmd_log_output)

        self.installation_folder = self.load_config()

        self.current_install_path = QLabel(f"<b>Install Path:</b> {self.installation_folder}")
        self.layout.addWidget(self.current_install_path)

        # Select Installation Folder Button
        self.folder_button = QPushButton("Select Brotato Installation Folder", self)
        self.folder_button.clicked.connect(self.select_installation_folder)
        self.layout.addWidget(self.folder_button)

        self.download_url_layout = QHBoxLayout()
        # Input for URL
        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("Paste Workshop URL here...")
        self.url_input.setEnabled(self.installation_folder is not None)
        self.url_input.setPlaceholderText("Paste Workshop Item URL")
        self.download_url_layout.addWidget(self.url_input)

        # Add Button
        self.add_button = QPushButton("Download Workshop Item", self)
        self.add_button.clicked.connect(self.add_to_queue)
        self.add_button.setEnabled(self.installation_folder is not None)
        self.download_url_layout.addWidget(self.add_button)

        self.layout.addLayout(self.download_url_layout)

        # Progress list
        self.queue_list_label = QLabel("<b>Download Queue:</b>", self)
        self.layout.addWidget(self.queue_list_label)
        self.queue_list = QListWidget(self)
        self.layout.addWidget(self.queue_list)

        # Log Output
        self.logs_label = QLabel("<b>Logs (Application + SteamCMD):</b>", self)
        self.layout.addWidget(self.logs_label)
        self.layout.addLayout(self.logs_layout)

        # Open Workshop Page Button
        self.open_workshop_button = QPushButton("Open Steam Workshop Page", self)
        self.open_workshop_button.clicked.connect(self.open_workshop_page)
        self.layout.addWidget(self.open_workshop_button)

        # Set Layout
        self.setLayout(self.layout)
    
    def open_workshop_page(self):
        """Open the Steam Workshop page for Brotato."""
        url = "https://steamcommunity.com/app/1942280/workshop/"
        QDesktopServices.openUrl(QUrl(url))
    
    def select_installation_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Installation Folder")
        if folder:
            if os.path.exists(os.path.join(folder, "Brotato.exe")):
                self.installation_folder = folder
                self.log_output.append(f"<b>Set installation folder:</b> {self.installation_folder}")
                self.url_input.setEnabled(True)
                self.add_button.setEnabled(True)  # Enable Add to Queue button
                self.current_install_path.setText(f"<b>Install Path:</b> {self.installation_folder}")
                self.save_config()
            else:
                self.installation_folder = None
                self.log_output.append("<b>Error:</b> Selected folder does not contain 'Brotato.exe'.")
                self.add_button.setEnabled(False)  # Disable Add to Queue button
        else:
            self.log_output.append("</b>No folder selected.</b>")
            self.url_input.setEnabled(False)
            self.add_button.setEnabled(False)  # Ensure button stays disabled


    def add_to_queue(self):
        url = self.url_input.text()
        # Extract game_id and item_id from URL
        try:
            item_name, game_id, item_id = self.parse_url(url)
            self.log_output.append(f"<b>Added Item Name:</b> {item_name}, <b>Item ID:</b> {item_id}")
            self.add_to_download_queue(item_name, item_id)
            self.start_download(game_id, item_id)
        except ValueError as e:
            self.log_output.append(f"<b>Error:</b> {str(e)}")

    def add_to_download_queue(self, item_name, item_id):
        # Add a new entry to the queue with the URL and set its status to "In Progress"
        self.download_queue.append({"item_name": item_name, "item_id": item_id, "status": "Downloading..."})
        self.update_queue_list()
    
    def update_queue_list(self):
        """Update the list widget to show the current download statuses."""
        self.queue_list.clear()
        for entry in self.download_queue:
            self.queue_list.addItem(f"{entry['item_name']} ({entry['item_id']}) - {entry['status']}")

    def parse_url(self, url):
        # Validate and extract item_id from the Steam Workshop URL
        if "steamcommunity.com" not in url or "sharedfiles/filedetails" not in url:
            raise ValueError("Invalid URL format. Ensure it's a Steam Workshop item URL.")

        # Extract the item ID from the URL
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        item_id = query_params.get("id", [None])[0]
        if not item_id:
            raise ValueError("Invalid URL: 'id' parameter is missing.")
        
        # Fetch the page HTML to validate the app ID
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            app_element = soup.find("div", id="sharedfiles_content_ctn")
            if not app_element:
                raise ValueError("Could not find the game information on the page.")
            
            title_element = soup.find("div", class_="workshopItemTitle")
            title = "Unable to find mod title"
            if title_element:
                title = title_element.text.strip()

            app_id = app_element.get("data-miniprofile-appid", None)
            if app_id != "1942280":
                raise ValueError("The item does not belong to Brotato. (AppID: {})".format(app_id))
        except requests.RequestException as e:
            raise ValueError(f"Failed to fetch the URL: {e}")

        return title, "1942280", item_id

    def start_download(self, game_id, item_id):
        steamcmd_path = self.get_steamcmd_path()
        download_path = os.path.join(os.getcwd(), 'downloads')
        os.makedirs(download_path, exist_ok=True)
        self.log_output.append(f"<b>Downloading to</b> {download_path}")

        # Start Download Thread
        self.thread = DownloadThread(game_id, item_id, download_path, steamcmd_path)
        self.thread.progress.connect(self.update_progress)
        self.thread.log.connect(self.update_steamcmd_log)
        self.thread.finished.connect(lambda: self.download_complete(game_id, item_id))  # Trigger copy and status update
        self.thread.start()

    def download_complete(self, game_id, item_id):
        self.copy_to_brotato_mods(game_id, item_id)

        for entry in self.download_queue:
            if entry['item_id'] == item_id:
                entry['status'] = "Done"
        self.update_queue_list()

    def ensure_steamcmd_exists(self):
        """Check if SteamCMD is available, download and extract it if missing."""
        steamcmd_folder = os.path.join(os.getcwd(), "steamcmd")
        system = platform.system()

        if system == "Windows":
            steamcmd_folder += "/windows"
            url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
            file_path = os.path.join(steamcmd_folder, "steamcmd.zip")
            executable = os.path.join(steamcmd_folder, "steamcmd.exe")
        elif system == "Linux":
            steamcmd_folder += "/linux"
            url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
            file_path = os.path.join(steamcmd_folder, "steamcmd_linux.tar.gz")
            executable = os.path.join(steamcmd_folder, "steamcmd.sh")
        elif system == "Darwin":
            steamcmd_folder += "/macos"
            url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz"
            file_path = os.path.join(steamcmd_folder, "steamcmd_osx.tar.gz")
            executable = os.path.join(steamcmd_folder, "steamcmd.sh")
        else:
            raise OSError("Unsupported OS")
        
        os.makedirs(steamcmd_folder, exist_ok=True)

        # Check if the executable exists
        if os.path.exists(executable):
            self.log_output.append("<b>SteamCMD is already downloaded and ready.</b>")
            return executable

        # Download SteamCMD
        self.log_output.append(f"<b>Downloading SteamCMD from</b> {url}...")
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            self.log_output.append("<b>SteamCMD download complete.</b>")
        except Exception as e:
            self.log_output.append(f"<b>Failed to download SteamCMD:</b> {e}")
            return None

        # Extract the archive
        try:
            self.log_output.append("<b>Extracting SteamCMD...</b>")
            if file_path.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(steamcmd_folder)
            elif file_path.endswith(".tar.gz"):
                with tarfile.open(file_path, "r:gz") as tar_ref:
                    tar_ref.extractall(steamcmd_folder)
            else:
                raise ValueError("Unknown file format")
            self.log_output.append("<b>SteamCMD extraction complete.</b>")
        except Exception as e:
            self.log_output.append(f"<b>Failed to extract SteamCMD:</b> {e}")
            return None

        # Clean up the archive file
        os.remove(file_path)
        return executable
    
    def load_config(self):
        """Load configuration from file."""
        if not os.path.exists(CONFIG_FILE):
            return None

        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            installation_folder = config.get("installation_folder")
            if installation_folder and os.path.exists(os.path.join(installation_folder, "Brotato.exe")):
                self.log_output.append(f"<b>Set installation folder:</b> {installation_folder}")
                return installation_folder
            else:
                self.log_output.append("<b>Saved folder is invalid or does not contain 'Brotato.exe'.</b>")
                return None
        except Exception as e:
            self.log_output.append(f"<b>Failed to load config:</b> {e}")
            return None

    def save_config(self):
        """Save configuration to file."""
        if self.installation_folder:
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump({"installation_folder": self.installation_folder}, f)
                self.log_output.append(f"<b>Installation folder saved:</b> {self.installation_folder}")
            except Exception as e:
                self.log_output.append(f"<b>Failed to save config:</b> {e}")

    def get_steamcmd_path(self):
        return self.ensure_steamcmd_exists()
        

    def update_progress(self, value):
        # Update progress bar in the UI
        pass  # Implement as needed

    def update_steamcmd_log(self, message):
        # Append log messages
        self.steamcmd_log_output.append(message)

    def copy_to_brotato_mods(self, game_id, item_id):
        """Copies downloaded files to the Brotato mods folder."""
        if not self.installation_folder:
            self.log_output.append("<b>Error:</b> Installation folder is not set.")
            return
        
        # Paths
        steamcmd_download_path = os.path.join(
            os.getcwd(), "downloads", "steamapps", "workshop", "content", game_id, item_id
        )
        brotato_mods_path = os.path.join(self.installation_folder, "mods")

        if not os.path.exists(steamcmd_download_path):
            self.log_output.append(f"<b>Error:</b> Downloaded files not found at {steamcmd_download_path}")
            return

        # Ensure the mods folder exists
        os.makedirs(brotato_mods_path, exist_ok=True)

        try:
            # Copy all files and directories
            for item in os.listdir(steamcmd_download_path):
                source = os.path.join(steamcmd_download_path, item)
                destination = os.path.join(brotato_mods_path, item)

                if os.path.isdir(source):
                    shutil.copytree(source, destination, dirs_exist_ok=True)
                else:
                    shutil.copy2(source, destination)

            self.log_output.append(f"<b>Successfully copied mod files to</b> {brotato_mods_path}")
        except Exception as e:
            self.log_output.append(f"<b>Error copying files:</b> {e}")

# Main Application Execution
if __name__ == "__main__":
    app = QApplication([])
    downloader = SteamWorkshopDownloader()
    downloader.show()
    app.exec()
