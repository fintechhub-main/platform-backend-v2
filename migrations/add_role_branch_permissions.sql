CREATE TABLE IF NOT EXISTS role_branch_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role VARCHAR(50) NOT NULL,
    branch_id UUID NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_role_branch UNIQUE (role, branch_id)
);
