// Tauri requires main.rs for the binary entry point.
// The app logic lives in lib.rs.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    scanify_lib::run();
}
