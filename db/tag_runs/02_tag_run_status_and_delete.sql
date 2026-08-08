-- =====================================================================
-- Tag runs: status override and delete
-- SQL Server, same database as dbo.get_tag_runs_paginated
-- =====================================================================

IF OBJECT_ID('dbo.update_tag_run_status', 'P') IS NOT NULL
    DROP PROCEDURE dbo.update_tag_run_status;
GO

-- Forces a run into a given status. Used to park runs stuck in 'started'
-- as 'Deprecated' so they stop looking like work in progress.
CREATE PROCEDURE dbo.update_tag_run_status
    @id     INT,
    @status VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.tag_runs
       SET status           = @status,
           last_update_time = GETDATE()
     WHERE id = @id;

    SELECT @@ROWCOUNT AS affected_rows;
END
GO

IF OBJECT_ID('dbo.delete_tag_run', 'P') IS NOT NULL
    DROP PROCEDURE dbo.delete_tag_run;
GO

CREATE PROCEDURE dbo.delete_tag_run
    @id INT
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM dbo.tag_runs
     WHERE id = @id;

    SELECT @@ROWCOUNT AS affected_rows;
END
GO
