//! Scanify Desktop Application
//!
//! Tauri backend for the Scanify trading scanner.
//! Handles system tray, notifications, and native integrations.

#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem,
};

/// Create the system tray menu
fn create_tray_menu() -> SystemTrayMenu {
    let show = CustomMenuItem::new("show".to_string(), "Show Scanify");
    let hide = CustomMenuItem::new("hide".to_string(), "Hide");
    let separator = SystemTrayMenuItem::Separator;
    let start_scanner = CustomMenuItem::new("start".to_string(), "Start Scanner");
    let stop_scanner = CustomMenuItem::new("stop".to_string(), "Stop Scanner");
    let quit = CustomMenuItem::new("quit".to_string(), "Quit");

    SystemTrayMenu::new()
        .add_item(show)
        .add_item(hide)
        .add_native_item(separator)
        .add_item(start_scanner)
        .add_item(stop_scanner)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit)
}

/// Handle system tray events
fn handle_tray_event(app: &tauri::AppHandle, event: SystemTrayEvent) {
    match event {
        SystemTrayEvent::LeftClick { .. } => {
            // Show window on left click
            if let Some(window) = app.get_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
        SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
            "show" => {
                if let Some(window) = app.get_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "hide" => {
                if let Some(window) = app.get_window("main") {
                    let _ = window.hide();
                }
            }
            "start" => {
                // Emit event to frontend to start scanner
                if let Some(window) = app.get_window("main") {
                    let _ = window.emit("scanner-control", "start");
                }
            }
            "stop" => {
                // Emit event to frontend to stop scanner
                if let Some(window) = app.get_window("main") {
                    let _ = window.emit("scanner-control", "stop");
                }
            }
            "quit" => {
                std::process::exit(0);
            }
            _ => {}
        },
        _ => {}
    }
}

/// Send a desktop notification
#[tauri::command]
fn send_notification(title: String, body: String) -> Result<(), String> {
    tauri::api::notification::Notification::new("com.scanify.app")
        .title(&title)
        .body(&body)
        .show()
        .map_err(|e| e.to_string())
}

/// Get system information
#[tauri::command]
fn get_system_info() -> serde_json::Value {
    serde_json::json!({
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "version": env!("CARGO_PKG_VERSION"),
    })
}

fn main() {
    let tray = SystemTray::new().with_menu(create_tray_menu());

    tauri::Builder::default()
        .system_tray(tray)
        .on_system_tray_event(handle_tray_event)
        .invoke_handler(tauri::generate_handler![
            send_notification,
            get_system_info,
        ])
        .on_window_event(|event| {
            // Hide instead of close when clicking X
            if let tauri::WindowEvent::CloseRequested { api, .. } = event.event() {
                event.window().hide().unwrap();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
