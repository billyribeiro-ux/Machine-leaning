//! Scanify Desktop Application — Tauri v2 backend
//!
//! Provides native desktop capabilities:
//! - System tray with scanner controls
//! - Native OS notifications for high-priority alerts
//! - System info for platform detection
//!
//! The same SvelteKit frontend serves both browser and desktop.

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};

#[tauri::command]
fn send_notification(app: tauri::AppHandle, title: String, body: String) -> Result<(), String> {
    use tauri_plugin_notification::NotificationExt;
    app.notification()
        .builder()
        .title(&title)
        .body(&body)
        .show()
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_system_info() -> serde_json::Value {
    serde_json::json!({
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "version": env!("CARGO_PKG_VERSION"),
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![send_notification, get_system_info])
        .setup(|app| {
            // Build tray menu
            let show_i = MenuItem::with_id(app, "show", "Show Scanify", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "Hide", true, None::<&str>)?;
            let start_i =
                MenuItem::with_id(app, "start", "Start Scanner", true, None::<&str>)?;
            let stop_i =
                MenuItem::with_id(app, "stop", "Stop Scanner", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

            let menu = Menu::with_items(
                app,
                &[&show_i, &hide_i, &start_i, &stop_i, &quit_i],
            )?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("Scanify")
                .on_menu_event(|app, event| {
                    let id = event.id.as_ref();
                    match id {
                        "show" => {
                            if let Some(w) = app.get_webview_window("main") {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                        "hide" => {
                            if let Some(w) = app.get_webview_window("main") {
                                let _ = w.hide();
                            }
                        }
                        "start" => {
                            if let Some(w) = app.get_webview_window("main") {
                                let _ = w.emit("scanner-control", "start");
                            }
                        }
                        "stop" => {
                            if let Some(w) = app.get_webview_window("main") {
                                let _ = w.emit("scanner-control", "stop");
                            }
                        }
                        "quit" => {
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // Hide instead of close when user clicks X
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
