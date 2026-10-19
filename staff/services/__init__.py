from __future__ import annotations

from .staff_service import (ALLOWED_BY_CALLER, ROLE_MODEL_MAP,
                            StaffCreationResult, StaffUpdateResult,
                            _check_caller, _check_manager_scope,
                            _check_vendor_reassignment,
                            _get_existing_staff_flags, _normalize_email,
                            _normalize_role, _validate_bijouterie,
                            _validate_bijouteries, _validate_target_user,
                            create_staff_member, promote_user_to_admin,
                            update_staff_member)
