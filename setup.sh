#!/bin/bash

# Define variables
SERVICE_NAME="bratwurstpower"
USERNAME="$SERVICE_NAME"
BASEDIR="/opt/$SERVICE_NAME"
VENVDIR="$BASEDIR/venv"
TARGETDIR="$BASEDIR/app"
SOURCEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICEFILE="$SOURCEDIR/$SERVICE_NAME.service"
REQUIREMENTS_FILE="$SOURCEDIR/requirements.txt"
SYSTEMD_SERVICE_FILE="/usr/lib/systemd/system/$SERVICE_NAME.service"
CONFIG_FILE="$SOURCEDIR/$SERVICE_NAME.example.ini"
CONFIG_DEST="/etc/$SERVICE_NAME.ini"

# Function to install and set up the service
install_service() {
    # Create system user without login shell
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$USERNAME" || true

    # Set up directory structure and permissions
    sudo mkdir -p "$TARGETDIR"
    sudo chown -R "$USERNAME":"$USERNAME" "$BASEDIR"

    # Create Python virtual environment
    sudo -u "$USERNAME" python3 -m venv "$VENVDIR"

    # Install packages from requirements.txt if it exists
    if [ -f "$REQUIREMENTS_FILE" ]; then
        sudo -u "$USERNAME" "$VENVDIR/bin/pip" install -r "$REQUIREMENTS_FILE"
    fi

    # Copy Python files from source directory to target directory
    sudo cp "$SOURCEDIR"/*.py "$TARGETDIR"
    sudo chown "$USERNAME":"$USERNAME" "$TARGETDIR"/*.py

    # Copy .ini file to /etc
    copy_config_file

    # Copy and enable systemd service
    sudo cp "$SERVICEFILE" "$SYSTEMD_SERVICE_FILE"
    sudo chmod 644 "$SYSTEMD_SERVICE_FILE"
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME.service"

    echo "Setup complete. $SERVICE_NAME service is now running."
}

# Function to update the service
update_service() {
    echo "Updating $SERVICE_NAME..."

    # Overwrite the service file
    sudo cp "$SERVICEFILE" "$SYSTEMD_SERVICE_FILE"
    sudo chmod 644 "$SYSTEMD_SERVICE_FILE"
    sudo systemctl daemon-reload

    # Overwrite Python scripts
    sudo cp "$SOURCEDIR"/*.py "$TARGETDIR"
    sudo chown "$USERNAME":"$USERNAME" "$TARGETDIR"/*.py

    # Install packages from requirements.txt if it exists
    if [ -f "$REQUIREMENTS_FILE" ]; then
        sudo -u "$USERNAME" "$VENVDIR/bin/pip" install --upgrade --no-cache-dir -r "$REQUIREMENTS_FILE"
    fi

    # Ask if the .ini file should be replaced
    if [ -f "$CONFIG_FILE" ]; then
        read -rp "Do you want to replace the existing configuration file at $CONFIG_DEST? (y/N): " REPLACE_CONFIG
        if [[ "$REPLACE_CONFIG" =~ ^[Yy]$ ]]; then
            copy_config_file
        else
            echo "Keeping existing configuration file."
        fi
    else
        copy_config_file
    fi

    echo "$SERVICE_NAME has been updated."
}

# Function to copy .ini file to /etc
copy_config_file() {
    if [ -f "$CONFIG_FILE" ]; then
        sudo cp "$CONFIG_FILE" "$CONFIG_DEST"  # Change the destination name if needed
        echo "Configuration file copied to $CONFIG_DEST"
    else
        echo "No configuration file found at $CONFIG_FILE. Skipping copy."
    fi
}

# Function to uninstall and remove the service
uninstall_service() {
    # Stop and disable the systemd service
    sudo systemctl stop "$SERVICE_NAME.service"
    sudo systemctl disable "$SERVICE_NAME.service"

    # Remove the service file and reload systemd
    sudo rm -f "$SYSTEMD_SERVICE_FILE"
    sudo systemctl daemon-reload
    sudo systemctl reset-failed

    # Delete application files and virtual environment
    sudo rm -rf "$BASEDIR"

    # Delete the system user
    sudo userdel "$USERNAME"

    # Remove the .ini file from /etc
    sudo rm -f "$CONFIG_DEST"

    echo "Uninstallation complete. All $SERVICE_NAME components have been removed."
}

# Main script logic
if [ "$1" == "uninstall" ]; then
    uninstall_service
else
    # Check if the service is already installed
    if systemctl list-units --full --all | grep -q "$SERVICE_NAME.service"; then
        update_service
    else
        install_service
    fi
fi
