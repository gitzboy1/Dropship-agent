import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


class PlatformStore:
    def __init__(self, store_path: Optional[str] = None):
        self.store_path = store_path or os.environ.get(
            "LOCAL_PLATFORM_STORE",
            os.path.join(os.getcwd(), "data", "platform_store.json"),
        )
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        self._lock = threading.Lock()
        self._init_store()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "users": [],
            "workspaces": [],
            "workspace_snapshots": [],
            "audit_events": [],
            "agent_tasks": [],
            "usage_events": [],
        }

    def _init_store(self):
        if not os.path.exists(self.store_path):
            self._write_state(self._default_state())

    def _read_state(self) -> Dict[str, Any]:
        with open(self.store_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_state(self, state: Dict[str, Any]):
        with open(self.store_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)

    def _save(self, mutator):
        with self._lock:
            state = self._read_state()
            result = mutator(state)
            self._write_state(state)
            return result

    def register_user(self, email: str, password: str, full_name: str) -> Dict[str, Any]:
        email = email.strip().lower()
        if not email or not password or not full_name.strip():
            raise ValueError("Email, password, and full name are required.")

        def mutate(state):
            if any(user["email"] == email for user in state["users"]):
                raise ValueError("An account with this email already exists.")
            user = {
                "id": str(uuid.uuid4()),
                "email": email,
                "password_hash": generate_password_hash(password),
                "full_name": full_name.strip(),
                "role": "owner",
                "created_at": _utcnow(),
                "last_login_at": None,
            }
            state["users"].append(user)
            return user

        user = self._save(mutate)
        workspace = self.create_workspace(user["id"], f"{full_name.strip().split()[0]}'s Workspace")
        return {"user": self._public_user(user), "workspace": workspace}

    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        email = email.strip().lower()

        def mutate(state):
            for user in state["users"]:
                if user["email"] == email and check_password_hash(user["password_hash"], password):
                    user["last_login_at"] = _utcnow()
                    return self._public_user(user)
            return None

        return self._save(mutate)

    def _public_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "created_at": user["created_at"],
            "last_login_at": user.get("last_login_at"),
        }

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        state = self._read_state()
        for user in state["users"]:
            if user["id"] == user_id:
                return self._public_user(user)
        return None

    def list_workspaces(self, user_id: str) -> List[Dict[str, Any]]:
        state = self._read_state()
        return [
            workspace
            for workspace in sorted(state["workspaces"], key=lambda item: item["updated_at"], reverse=True)
            if workspace["user_id"] == user_id
        ]

    def create_workspace(
        self,
        user_id: str,
        name: str,
        country: str = "IN",
        niche: str = "",
        monthly_budget: float = 0,
    ) -> Dict[str, Any]:
        workspace = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name.strip() or "Workspace",
            "country": country,
            "niche": niche.strip(),
            "monthly_budget": monthly_budget,
            "store_stage": "idea",
            "settings": {
                "approval_level": "confirm",
                "target_margin": 35,
                "channels": ["facebook", "instagram"],
            },
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
        }

        def mutate(state):
            state["workspaces"].append(workspace)
            return workspace

        self._save(mutate)
        self.append_audit_event(
            workspace["id"],
            actor="system",
            event_type="workspace.created",
            payload={"name": workspace["name"], "country": country, "niche": niche},
        )
        return workspace

    def get_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        state = self._read_state()
        for workspace in state["workspaces"]:
            if workspace["id"] == workspace_id:
                return workspace
        return None

    def update_workspace(self, workspace_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def mutate(state):
            for workspace in state["workspaces"]:
                if workspace["id"] == workspace_id:
                    for field in ["name", "country", "niche", "monthly_budget", "store_stage"]:
                        if field in updates:
                            workspace[field] = updates[field]
                    if "settings" in updates:
                        workspace["settings"] = updates["settings"]
                    workspace["updated_at"] = _utcnow()
                    return workspace
            return None

        workspace = self._save(mutate)
        if workspace:
            self.append_audit_event(workspace_id, actor="user", event_type="workspace.updated", payload=updates)
        return workspace

    def save_workspace_snapshot(self, workspace_id: str, session_state: Dict[str, Any]) -> str:
        snapshot = {
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "session_state": session_state,
            "created_at": _utcnow(),
        }

        def mutate(state):
            state["workspace_snapshots"].append(snapshot)
            state["workspace_snapshots"] = state["workspace_snapshots"][-200:]
            return snapshot["id"]

        return self._save(mutate)

    def get_latest_workspace_snapshot(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        state = self._read_state()
        snapshots = [item for item in state["workspace_snapshots"] if item["workspace_id"] == workspace_id]
        if not snapshots:
            return None
        return sorted(snapshots, key=lambda item: item["created_at"], reverse=True)[0]

    def append_audit_event(self, workspace_id: str, actor: str, event_type: str, payload: Dict[str, Any]) -> str:
        event = {
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "actor": actor,
            "event_type": event_type,
            "payload": payload,
            "created_at": _utcnow(),
        }

        def mutate(state):
            state["audit_events"].append(event)
            state["audit_events"] = state["audit_events"][-500:]
            return event["id"]

        return self._save(mutate)

    def list_audit_events(self, workspace_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        state = self._read_state()
        items = [item for item in state["audit_events"] if item["workspace_id"] == workspace_id]
        return sorted(items, key=lambda item: item["created_at"], reverse=True)[:limit]

    def create_task(
        self,
        workspace_id: str,
        title: str,
        task_type: str,
        status: str = "queued",
        owner_agent: str = "general",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task = {
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "title": title,
            "task_type": task_type,
            "status": status,
            "owner_agent": owner_agent,
            "details": details or {},
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
        }

        def mutate(state):
            state["agent_tasks"].append(task)
            return task

        self._save(mutate)
        self.append_audit_event(workspace_id, "system", "task.created", {"title": title, "task_type": task_type})
        return task

    def list_tasks(self, workspace_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        state = self._read_state()
        tasks = [item for item in state["agent_tasks"] if item["workspace_id"] == workspace_id]
        return sorted(tasks, key=lambda item: item["updated_at"], reverse=True)[:limit]

    def update_task(self, workspace_id: str, task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def mutate(state):
            for task in state["agent_tasks"]:
                if task["workspace_id"] == workspace_id and task["id"] == task_id:
                    for field in ["title", "task_type", "status", "owner_agent"]:
                        if field in updates:
                            task[field] = updates[field]
                    if "details" in updates:
                        task["details"] = updates["details"]
                    task["updated_at"] = _utcnow()
                    return task
            return None

        task = self._save(mutate)
        if task:
            self.append_audit_event(workspace_id, "user", "task.updated", {"task_id": task_id, **updates})
        return task

    def record_usage(self, workspace_id: str, event_kind: str, units: int = 1, metadata: Optional[Dict[str, Any]] = None):
        event = {
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "event_kind": event_kind,
            "units": units,
            "metadata": metadata or {},
            "created_at": _utcnow(),
        }

        def mutate(state):
            state["usage_events"].append(event)
            state["usage_events"] = state["usage_events"][-1000:]
            return None

        self._save(mutate)

    def get_dashboard_summary(self, workspace_id: str) -> Dict[str, Any]:
        state = self._read_state()
        tasks = [item for item in state["agent_tasks"] if item["workspace_id"] == workspace_id]
        usage = [item for item in state["usage_events"] if item["workspace_id"] == workspace_id]
        audits = [item for item in state["audit_events"] if item["workspace_id"] == workspace_id]
        snapshot = self.get_latest_workspace_snapshot(workspace_id) or {"session_state": {}}
        session_state = snapshot["session_state"]

        tasks_by_status: Dict[str, int] = {}
        for task in tasks:
            tasks_by_status[task["status"]] = tasks_by_status.get(task["status"], 0) + 1

        usage_by_kind: Dict[str, int] = {}
        for item in usage:
            usage_by_kind[item["event_kind"]] = usage_by_kind.get(item["event_kind"], 0) + item["units"]

        return {
            "tasks_by_status": tasks_by_status,
            "usage_by_kind": usage_by_kind,
            "audit_event_count": len(audits),
            "products_found": len(session_state.get("products_found", [])),
            "actions_logged": len(session_state.get("actions", [])),
            "budget": session_state.get("budget", 0),
            "spent": session_state.get("spent", 0),
        }


platform_store = PlatformStore()
