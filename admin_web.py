import argparse
import os
from functools import wraps
from typing import Callable, Dict, Optional

from flask import Flask, abort, flash, g, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("ADMIN_WEB_SECRET") or os.getenv("BOT_TOKEN") or "dev-secret"

    @app.before_request
    def load_admin():
        admin_id = session.get("admin_id")
        g.admin = db.get_admin_user_by_id(admin_id) if admin_id else None
        g.permissions = set()
        if g.admin:
            g.permissions = set(db.get_role_permissions(g.admin["role_id"]))

    def login_required(view: Callable):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not g.admin:
                return redirect(url_for("admin_login"))
            return view(*args, **kwargs)

        return wrapper

    def permission_required(permission: str):
        def decorator(view: Callable):
            @wraps(view)
            def wrapper(*args, **kwargs):
                if not g.admin:
                    return redirect(url_for("admin_login"))
                if permission not in g.permissions:
                    abort(403)
                return view(*args, **kwargs)

            return wrapper

        return decorator

    def audit(action: str, entity_type: Optional[str] = None, entity_id: Optional[str] = None, meta: Optional[Dict] = None):
        db.log_admin_action(
            actor_id=g.admin["id"] if g.admin else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            meta=meta,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=request.headers.get("User-Agent"),
        )

    @app.get("/admin/login")
    def admin_login():
        return render_template("admin/login.html")

    @app.post("/admin/login")
    def admin_login_post():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = db.get_admin_user_by_username(username)
        if not admin or not admin.get("is_active"):
            flash("Неверные учетные данные.", "error")
            return redirect(url_for("admin_login"))
        if not check_password_hash(admin["password_hash"], password):
            flash("Неверные учетные данные.", "error")
            return redirect(url_for("admin_login"))
        session["admin_id"] = admin["id"]
        db.update_admin_last_login(admin["id"])
        g.admin = admin
        audit("login", "admin_user", str(admin["id"]))
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/logout")
    @login_required
    def admin_logout():
        audit("logout", "admin_user", str(g.admin["id"]))
        session.clear()
        return redirect(url_for("admin_login"))

    @app.get("/admin")
    @permission_required("admin.view_dashboard")
    def admin_dashboard():
        stats = db.get_admin_dashboard_stats()
        return render_template("admin/dashboard.html", stats=stats)

    @app.get("/admin/users")
    @permission_required("admin.manage_admins")
    def admin_users():
        users = db.list_admin_users()
        roles = db.list_admin_roles()
        return render_template("admin/users.html", users=users, roles=roles)

    @app.post("/admin/users")
    @permission_required("admin.manage_admins")
    def admin_users_create():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role_id = int(request.form.get("role_id", "0"))
        if not username or not password or not role_id:
            flash("Заполните все поля.", "error")
            return redirect(url_for("admin_users"))
        password_hash = generate_password_hash(password)
        admin_id = db.create_admin_user(username, password_hash, role_id)
        audit("create_admin", "admin_user", str(admin_id), {"username": username, "role_id": role_id})
        flash("Администратор создан.", "success")
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:admin_id>/toggle")
    @permission_required("admin.manage_admins")
    def admin_users_toggle(admin_id: int):
        target = db.get_admin_user_by_id(admin_id)
        if not target:
            abort(404)
        new_state = not bool(target["is_active"])
        db.set_admin_user_active(admin_id, new_state)
        audit("toggle_admin", "admin_user", str(admin_id), {"is_active": new_state})
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:admin_id>/role")
    @permission_required("admin.manage_admins")
    def admin_users_role(admin_id: int):
        role_id = int(request.form.get("role_id", "0"))
        if not role_id:
            abort(400)
        db.set_admin_user_role(admin_id, role_id)
        audit("change_admin_role", "admin_user", str(admin_id), {"role_id": role_id})
        return redirect(url_for("admin_users"))

    @app.get("/admin/companies")
    @permission_required("companies.view")
    def admin_companies():
        search = request.args.get("search", "").strip() or None
        companies = db.list_companies_admin(search=search)
        return render_template("admin/companies.html", companies=companies, search=search)

    @app.post("/admin/companies/<int:company_id>/block")
    @permission_required("companies.manage")
    def admin_companies_block(company_id: int):
        blocked = request.form.get("blocked") == "1"
        db.update_company_blocked(company_id, blocked)
        audit("company_block", "company", str(company_id), {"blocked": blocked})
        return redirect(url_for("admin_companies"))

    @app.post("/admin/companies/<int:company_id>/subscription")
    @permission_required("finance.manage")
    def admin_companies_subscription(company_id: int):
        level = request.form.get("subscription_level") or None
        until = request.form.get("subscription_until") or None
        db.update_company_subscription(company_id, level, until)
        audit(
            "company_subscription",
            "company",
            str(company_id),
            {"subscription_level": level, "subscription_until": until},
        )
        return redirect(url_for("admin_companies"))

    @app.get("/admin/masters")
    @permission_required("masters.view")
    def admin_masters():
        search = request.args.get("search", "").strip() or None
        masters = db.list_masters_admin(search=search)
        return render_template("admin/masters.html", masters=masters, search=search)

    @app.post("/admin/masters/<int:master_id>/block")
    @permission_required("masters.manage")
    def admin_masters_block(master_id: int):
        blocked = request.form.get("blocked") == "1"
        db.update_master_blocked(master_id, blocked)
        audit("master_block", "master", str(master_id), {"blocked": blocked})
        return redirect(url_for("admin_masters"))

    @app.post("/admin/masters/<int:master_id>/notes")
    @permission_required("support.manage")
    def admin_masters_notes(master_id: int):
        notes = request.form.get("notes")
        db.update_master_notes(master_id, notes)
        audit("master_notes", "master", str(master_id))
        return redirect(url_for("admin_masters"))

    @app.post("/admin/masters/<int:master_id>/passport")
    @permission_required("kyc.verify")
    def admin_masters_passport(master_id: int):
        locked = request.form.get("passport_locked") == "1"
        db.update_master_passport_locked(master_id, locked)
        audit("master_passport_lock", "master", str(master_id), {"passport_locked": locked})
        return redirect(url_for("admin_masters"))

    @app.get("/admin/appeals")
    @permission_required("appeals.view")
    def admin_appeals():
        status = request.args.get("status") or None
        appeals = db.list_review_appeals_admin(status=status)
        return render_template("admin/appeals.html", appeals=appeals, status=status)

    @app.post("/admin/appeals/<int:appeal_id>/decision")
    @permission_required("appeals.resolve")
    def admin_appeals_decision(appeal_id: int):
        status = request.form.get("status")
        comment = request.form.get("admin_comment")
        if status not in {"approved", "rejected", "deleted"}:
            abort(400)
        db.update_review_appeal_admin_decision(appeal_id, status, comment)
        audit("appeal_decision", "review_appeal", str(appeal_id), {"status": status})
        return redirect(url_for("admin_appeals"))

    @app.get("/admin/audit")
    @permission_required("audit.view")
    def admin_audit():
        entries = db.list_audit_log()
        return render_template("admin/audit.html", entries=entries)

    @app.get("/admin/analytics")
    @permission_required("analytics.view")
    def admin_analytics():
        stats = db.get_admin_dashboard_stats()
        return render_template("admin/analytics.html", stats=stats)

    @app.get("/admin/export/companies")
    @permission_required("data.export")
    def admin_export_companies():
        companies = db.list_companies_admin()
        audit("export_companies", "company")
        response = make_response(render_template("admin/export_companies.csv", companies=companies))
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=companies.csv"
        return response

    @app.get("/admin/export/masters")
    @permission_required("data.export")
    def admin_export_masters():
        masters = db.list_masters_admin()
        audit("export_masters", "master")
        response = make_response(render_template("admin/export_masters.csv", masters=masters))
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=masters.csv"
        return response

    return app


def cli_create_admin(username: str, password: str, role_name: str) -> None:
    db.init_db()
    roles = db.list_admin_roles()
    role = next((r for r in roles if r["name"] == role_name), None)
    if not role:
        raise SystemExit(f"Role '{role_name}' not found. Available: {[r['name'] for r in roles]}")
    admin_id = db.create_admin_user(username, generate_password_hash(password), role["id"])
    db.log_admin_action(admin_id, "bootstrap_admin", "admin_user", str(admin_id), {"username": username})
    print(f"Admin user created: {username} (id={admin_id}, role={role_name})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Admin web panel")
    subparsers = parser.add_subparsers(dest="command")

    create_admin = subparsers.add_parser("create-admin", help="Create admin user")
    create_admin.add_argument("--username", required=True)
    create_admin.add_argument("--password", required=True)
    create_admin.add_argument("--role", required=True)

    args = parser.parse_args()

    if args.command == "create-admin":
        cli_create_admin(args.username, args.password, args.role)
        return

    db.init_db()
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.getenv("ADMIN_WEB_PORT", "8080")))


if __name__ == "__main__":
    main()
