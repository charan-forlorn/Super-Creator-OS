use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AutosaveEnvelope {
    pub project_json: String,
    pub project_path: Option<String>,
    pub saved_at_ms: u128,
    pub project_id: String,
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

fn ensure_json_document(project_json: &str) -> Result<(), String> {
    serde_json::from_str::<serde_json::Value>(project_json)
        .map(|_| ())
        .map_err(|e| format!("invalid project JSON: {e}"))
}

fn write_synced(path: &Path, contents: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("create project directory failed: {e}"))?;
    }
    let mut file = File::create(path)
        .map_err(|e| format!("create project temp file failed: {e}"))?;
    file.write_all(contents.as_bytes())
        .map_err(|e| format!("write project temp file failed: {e}"))?;
    file.sync_all()
        .map_err(|e| format!("sync project temp file failed: {e}"))?;
    Ok(())
}

fn sibling_path(path: &Path, suffix: &str) -> PathBuf {
    let file_name = path
        .file_name()
        .and_then(|x| x.to_str())
        .unwrap_or("project.haip.json");
    path.with_file_name(format!("{file_name}{suffix}"))
}

pub fn save_project(path: &Path, project_json: &str) -> Result<(), String> {
    ensure_json_document(project_json)?;
    let tmp = sibling_path(path, ".tmp");
    let backup = sibling_path(path, ".bak");
    write_synced(&tmp, project_json)?;

    if path.exists() {
        if backup.exists() {
            fs::remove_file(&backup)
                .map_err(|e| format!("remove stale project backup failed: {e}"))?;
        }
        fs::rename(path, &backup)
            .map_err(|e| format!("rotate project backup failed: {e}"))?;
    }

    if let Err(error) = fs::rename(&tmp, path) {
        if backup.exists() && !path.exists() {
            let _ = fs::rename(&backup, path);
        }
        let _ = fs::remove_file(&tmp);
        return Err(format!("finalize project save failed: {error}"));
    }

    Ok(())
}

pub fn open_project(path: &Path) -> Result<String, String> {
    let contents = fs::read_to_string(path)
        .map_err(|e| format!("read project failed: {e}"))?;
    ensure_json_document(&contents)?;
    Ok(contents)
}

fn autosave_dir(base_dir: &Path) -> PathBuf {
    base_dir.join("haios-video-studio").join("autosave")
}

fn validate_project_id(project_id: &str) -> Result<(), String> {
    if project_id.is_empty()
        || !project_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err("invalid project id for autosave".to_string());
    }
    Ok(())
}

fn autosave_path(base_dir: &Path, project_id: &str) -> Result<PathBuf, String> {
    validate_project_id(project_id)?;
    Ok(autosave_dir(base_dir).join(format!("{project_id}.autosave.json")))
}

pub fn write_autosave(
    base_dir: &Path,
    project_id: &str,
    project_json: &str,
    project_path: Option<String>,
) -> Result<(), String> {
    ensure_json_document(project_json)?;
    let envelope = AutosaveEnvelope {
        project_json: project_json.to_string(),
        project_path,
        saved_at_ms: now_ms(),
        project_id: project_id.to_string(),
    };
    let serialized = serde_json::to_string_pretty(&envelope)
        .map_err(|e| format!("serialize autosave failed: {e}"))?;
    let path = autosave_path(base_dir, project_id)?;
    save_project(&path, &serialized)
}

pub fn clear_autosave(base_dir: &Path, project_id: &str) -> Result<bool, String> {
    let path = autosave_path(base_dir, project_id)?;
    let backup = sibling_path(&path, ".bak");
    let mut removed = false;
    for candidate in [&path, &backup] {
        if candidate.exists() {
            fs::remove_file(candidate)
                .map_err(|e| format!("clear autosave failed: {e}"))?;
            removed = true;
        }
    }
    Ok(removed)
}

pub fn latest_autosave(base_dir: &Path) -> Result<Option<AutosaveEnvelope>, String> {
    let dir = autosave_dir(base_dir);
    if !dir.exists() {
        return Ok(None);
    }
    let mut newest: Option<(SystemTime, PathBuf)> = None;
    for entry in fs::read_dir(&dir).map_err(|e| format!("read autosave directory failed: {e}"))? {
        let entry = entry.map_err(|e| format!("read autosave entry failed: {e}"))?;
        let path = entry.path();
        if !path
            .file_name()
            .and_then(|x| x.to_str())
            .map(|x| x.ends_with(".autosave.json"))
            .unwrap_or(false)
        {
            continue;
        }
        let modified = entry
            .metadata()
            .and_then(|m| m.modified())
            .unwrap_or(UNIX_EPOCH);
        if newest.as_ref().map(|(t, _)| modified > *t).unwrap_or(true) {
            newest = Some((modified, path));
        }
    }

    let Some((_, path)) = newest else {
        return Ok(None);
    };
    let contents = fs::read_to_string(path)
        .map_err(|e| format!("read autosave failed: {e}"))?;
    let envelope = serde_json::from_str::<AutosaveEnvelope>(&contents)
        .map_err(|e| format!("invalid autosave envelope: {e}"))?;
    ensure_json_document(&envelope.project_json)?;
    Ok(Some(envelope))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root(label: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "haios-project-io-{label}-{}-{}",
            std::process::id(),
            now_ms()
        ));
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn transactional_save_preserves_previous_bytes_as_backup() {
        let root = temp_root("save");
        let path = root.join("demo.haip.json");
        save_project(&path, r#"{"schemaVersion":1,"name":"old"}"#).unwrap();
        save_project(&path, r#"{"schemaVersion":1,"name":"new"}"#).unwrap();

        assert_eq!(open_project(&path).unwrap(), r#"{"schemaVersion":1,"name":"new"}"#);
        assert_eq!(
            fs::read_to_string(sibling_path(&path, ".bak")).unwrap(),
            r#"{"schemaVersion":1,"name":"old"}"#
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn invalid_json_never_replaces_existing_project() {
        let root = temp_root("invalid");
        let path = root.join("demo.haip.json");
        save_project(&path, r#"{"schemaVersion":1,"name":"safe"}"#).unwrap();

        let error = save_project(&path, "{not-json").unwrap_err();
        assert!(error.contains("invalid project JSON"));
        assert_eq!(open_project(&path).unwrap(), r#"{"schemaVersion":1,"name":"safe"}"#);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn autosave_roundtrips_path_and_can_be_cleared() {
        let root = temp_root("autosave");
        write_autosave(
            &root,
            "proj-123",
            r#"{"schemaVersion":1,"name":"recover"}"#,
            Some("C:/projects/demo.haip.json".to_string()),
        )
        .unwrap();

        let envelope = latest_autosave(&root).unwrap().unwrap();
        assert_eq!(envelope.project_id, "proj-123");
        assert_eq!(envelope.project_path.as_deref(), Some("C:/projects/demo.haip.json"));
        assert!(clear_autosave(&root, "proj-123").unwrap());
        assert!(latest_autosave(&root).unwrap().is_none());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn autosave_rejects_path_traversal_project_ids() {
        let root = temp_root("traversal");
        let error = write_autosave(&root, "../escape", r#"{"schemaVersion":1}"#, None)
            .unwrap_err();
        assert_eq!(error, "invalid project id for autosave");
        let _ = fs::remove_dir_all(root);
    }
}
