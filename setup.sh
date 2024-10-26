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
    echo "Create system user $USERNAME"
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$USERNAME" || true

    echo "Add user to group i2c"
    sudo usermod -aG i2c "$USERNAME"

    echo "Set up directory structure and permissions"
    sudo mkdir -p "$TARGETDIR"
    sudo chown -R "$USERNAME":"$USERNAME" "$BASEDIR"

    echo "Create Python virtual environment"
    sudo -u "$USERNAME" python3 -m venv "$VENVDIR"

    echo "Install packages from requirements.txt if needed"
    if [ -f "$REQUIREMENTS_FILE" ]; then
        sudo cp "$REQUIREMENTS_FILE" "$TARGETDIR"
        sudo -u "$USERNAME" "$VENVDIR/bin/pip" install --no-cache-dir -r "$TARGETDIR/requirements.txt"
    fi

    echo "Copy files to $TARGETDIR"
    sudo cp "$SOURCEDIR"/*.py "$TARGETDIR"
    sudo chown "$USERNAME":"$USERNAME" "$TARGETDIR"/*.py

    echo "Copy .ini file to /etc"
    copy_config_file

    echo "Install and enable systemd service"
    sudo cp "$SERVICEFILE" "$SYSTEMD_SERVICE_FILE"
    sudo chmod 644 "$SYSTEMD_SERVICE_FILE"
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME.service"

    echo "Setup complete. $SERVICE_NAME service is now running."
}

# Function to update the service
update_service() {
    echo "Updating $SERVICE_NAME..."
    cd "$SOURCEDIR" || exit

    echo "Update from git"
    git pull

    echo "Overwrite the service file"
    sudo cp "$SERVICEFILE" "$SYSTEMD_SERVICE_FILE"
    sudo chmod 644 "$SYSTEMD_SERVICE_FILE"
    sudo systemctl daemon-reload

    echo "Overwrite Python scripts"
    sudo cp "$SOURCEDIR"/*.py "$TARGETDIR"
    sudo chown "$USERNAME":"$USERNAME" "$TARGETDIR"/*.py

    echo "Install or update python packages if needed"
    if [ -f "$REQUIREMENTS_FILE" ]; then
        sudo cp "$REQUIREMENTS_FILE" "$TARGETDIR"
        sudo -u "$USERNAME" "$VENVDIR/bin/pip" install --upgrade --no-cache-dir -r "$TARGETDIR/requirements.txt"
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

    echo "Restarting the service"
    sudo systemctl restart "$SERVICE_NAME.service"

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
    echo "Stop and disable the systemd service"
    sudo systemctl stop "$SERVICE_NAME.service"
    sudo systemctl disable "$SERVICE_NAME.service"

    echo "Remove the service file and reload systemd"
    sudo rm -f "$SYSTEMD_SERVICE_FILE"
    sudo systemctl daemon-reload
    sudo systemctl reset-failed

    echo "Delete application files and virtual environment"
    sudo rm -rf "$BASEDIR"

    echo "Delete the system user"
    sudo userdel "$USERNAME"

    echo "Remove the .ini file from /etc"
    sudo rm -f "$CONFIG_DEST"

    echo "Uninstallation complete. All $SERVICE_NAME components have been removed."
}

# Main script logic
case "$1" in
    install)
        install_service
        ;;
    update)
        if systemctl list-units --full --all | grep -q "$SERVICE_NAME.service"; then
            update_service
        else
            echo "Service $SERVICE_NAME is not installed. Please run the script with 'install' to set it up."
        fi
        ;;
    uninstall)
        uninstall_service
        ;;
    *)
        echo "Usage: $0 {install|update|uninstall}"
        exit 1
        ;;
esac
