-- ============================================================================
-- SCRIPT KHỞI TẠO CƠ SỞ DỮ LIỆU ĐỘC LẬP (STANDALONE) CHO RAG VECTOR AI SERVICE
-- ============================================================================

-------------------------------------------------------------------------------
-- 1. TẠO CSDL [RagVectorDb] NẾU CHƯA TỒN TẠI
-------------------------------------------------------------------------------
IF DB_ID(N'RagVectorDb') IS NULL
BEGIN
    BEGIN TRY
        EXEC(N'CREATE DATABASE [RagVectorDb]');
        PRINT N'-> [OK] Đã tạo mới CSDL RagVectorDb thành công.';
    END TRY
    BEGIN CATCH
        PRINT N'-> [INFO] CSDL RagVectorDb đã tồn tại.';
    END CATCH
END
GO

IF DB_ID(N'RagVectorDb') IS NOT NULL
BEGIN
    USE [RagVectorDb];
END
GO

-------------------------------------------------------------------------------
-- 2. KHỞI TẠO 7 BẢNG CỐT LÕI
-------------------------------------------------------------------------------

-- 2.1 Bảng RagDocuments: Quản lý thông tin tài liệu upload, phân quyền & trạng thái
IF OBJECT_ID('dbo.RagDocuments', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.RagDocuments
    (
        Id INT IDENTITY(1,1) CONSTRAINT PK_RagDocuments PRIMARY KEY,
        DocumentName NVARCHAR(500) NOT NULL,
        FileName NVARCHAR(500) NOT NULL,
        FilePath NVARCHAR(1000) NOT NULL,
        FileSize BIGINT NOT NULL,
        Category NVARCHAR(200) NULL,
        OwnerDepartment NVARCHAR(200) NULL,
        Description NVARCHAR(MAX) NULL,
        Tags NVARCHAR(MAX) NULL,
        AccessScope VARCHAR(50) NOT NULL CONSTRAINT DF_RagDocuments_AccessScope DEFAULT 'Public',
        EffectiveDate DATETIME2 NULL,
        ExpirationDate DATETIME2 NULL,
        IngestStatus VARCHAR(50) NOT NULL CONSTRAINT DF_RagDocuments_IngestStatus DEFAULT 'Pending',
        IngestError NVARCHAR(MAX) NULL,
        ChunkCount INT NOT NULL CONSTRAINT DF_RagDocuments_ChunkCount DEFAULT 0,
        UploadedBy NVARCHAR(100) NULL,
        TenantId INT NULL,
        CreationTime DATETIME2 NOT NULL CONSTRAINT DF_RagDocuments_CreationTime DEFAULT GETUTCDATE(),
        LastModificationTime DATETIME2 NULL
    );
    CREATE INDEX IX_RagDocuments_AccessScope ON dbo.RagDocuments(AccessScope);
    CREATE INDEX IX_RagDocuments_IngestStatus ON dbo.RagDocuments(IngestStatus);
    PRINT N'-> [OK] Tạo bảng RagDocuments.';
END;

-- 2.2 Bảng RagDocumentRoles: Danh sách vai trò được phép truy cập theo từng tài liệu (RBAC)
IF OBJECT_ID('dbo.RagDocumentRoles', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.RagDocumentRoles
    (
        Id INT IDENTITY(1,1) CONSTRAINT PK_RagDocumentRoles PRIMARY KEY,
        RagDocumentId INT NOT NULL CONSTRAINT FK_RagDocumentRoles_RagDocuments REFERENCES dbo.RagDocuments(Id) ON DELETE CASCADE,
        RoleName NVARCHAR(200) NOT NULL
    );
    CREATE INDEX IX_RagDocumentRoles_RagDocumentId ON dbo.RagDocumentRoles(RagDocumentId);
    CREATE INDEX IX_RagDocumentRoles_RoleName ON dbo.RagDocumentRoles(RoleName);
    PRINT N'-> [OK] Tạo bảng RagDocumentRoles.';
END;

-- 2.3 Bảng IngestionFiles: Lưu vết trạng thái file ingestion và fingerprint chống trùng lặp
IF OBJECT_ID('dbo.IngestionFiles', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.IngestionFiles
    (
        relative_path NVARCHAR(400) NOT NULL CONSTRAINT PK_IngestionFiles PRIMARY KEY,
        source NVARCHAR(512) NOT NULL,
        last_write_time_utc DATETIME2 NOT NULL,
        length BIGINT NOT NULL,
        fingerprint NVARCHAR(1024) NOT NULL,
        status NVARCHAR(32) NOT NULL,
        chunk_count INT NOT NULL CONSTRAINT DF_IngestionFiles_chunk_count DEFAULT 0,
        updated_at_utc DATETIME2 NOT NULL,
        error NVARCHAR(MAX) NULL
    );
    PRINT N'-> [OK] Tạo bảng IngestionFiles.';
END;

-- 2.4 Bảng IngestionTasks: Quản lý tiến trình xử lý ngầm (Pending -> Processing -> Completed/Failed)
IF OBJECT_ID('dbo.IngestionTasks', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.IngestionTasks
    (
        Id INT IDENTITY(1,1) CONSTRAINT PK_IngestionTasks PRIMARY KEY,
        TaskId VARCHAR(36) NOT NULL CONSTRAINT UQ_IngestionTasks_TaskId UNIQUE,
        BackendDocumentId INT NULL,
        FileName NVARCHAR(500) NOT NULL,
        Status VARCHAR(50) NOT NULL CONSTRAINT DF_IngestionTasks_Status DEFAULT 'PENDING',
        ProgressPercent INT NOT NULL CONSTRAINT DF_IngestionTasks_ProgressPercent DEFAULT 0,
        ChunkCount INT NOT NULL CONSTRAINT DF_IngestionTasks_ChunkCount DEFAULT 0,
        ErrorMessage NVARCHAR(MAX) NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_IngestionTasks_CreatedAt DEFAULT GETUTCDATE(),
        UpdatedAt DATETIME2 NULL
    );
    CREATE INDEX IX_IngestionTasks_TaskId ON dbo.IngestionTasks(TaskId);
    PRINT N'-> [OK] Tạo bảng IngestionTasks.';
END;

-- 2.5 Bảng Documents: Lưu các chunk văn bản, metadata JSON và Vector 1024 chiều
IF OBJECT_ID('dbo.Documents', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Documents
    (
        id_int INT IDENTITY(1,1) CONSTRAINT PK_Documents PRIMARY KEY CLUSTERED,
        id VARCHAR(255) NOT NULL CONSTRAINT UQ_Documents_id UNIQUE,
        document NVARCHAR(MAX),
        metadata NVARCHAR(MAX),
        embedding VECTOR(1024)
    );
    PRINT N'-> [OK] Tạo bảng Documents (Vector 1024 dimensions).';
END;

-- 2.6 Bảng Conversations: Quản lý các phiên trò chuyện của người dùng
IF OBJECT_ID('dbo.Conversations', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Conversations
    (
        Id INT IDENTITY(1,1) CONSTRAINT PK_Conversations PRIMARY KEY,
        UserId NVARCHAR(200) NULL,
        UserRoles NVARCHAR(500) NULL,
        UserDepartment NVARCHAR(100) NULL,
        Title NVARCHAR(255) NULL CONSTRAINT DF_Conversations_Title DEFAULT N'Cuộc hội thoại mới',
        TitleSource VARCHAR(20) NOT NULL CONSTRAINT DF_Conversations_TitleSource DEFAULT 'default',
        IsPinned BIT NOT NULL CONSTRAINT DF_Conversations_IsPinned DEFAULT 0,
        PinnedAt DATETIME2 NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_Conversations_CreatedAt DEFAULT GETUTCDATE(),
        UpdatedAt DATETIME2 NOT NULL CONSTRAINT DF_Conversations_UpdatedAt DEFAULT GETUTCDATE()
    );
    CREATE INDEX IX_Conversations_UserId ON dbo.Conversations(UserId);
    CREATE INDEX IX_Conversations_User_Pinned_Updated ON dbo.Conversations(UserId, IsPinned, UpdatedAt DESC);
    PRINT N'-> [OK] Tạo bảng Conversations.';
END;

-- 2.7 Bảng ChatMessages: Lưu lịch sử tin nhắn kèm nguồn trích dẫn
IF OBJECT_ID('dbo.ChatMessages', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChatMessages
    (
        Id INT IDENTITY(1,1) CONSTRAINT PK_ChatMessages PRIMARY KEY,
        ConversationId INT NOT NULL CONSTRAINT FK_ChatMessages_Conversations REFERENCES dbo.Conversations(Id) ON DELETE CASCADE,
        Role VARCHAR(20) NOT NULL,
        Content NVARCHAR(MAX) NOT NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ChatMessages_CreatedAt DEFAULT GETUTCDATE()
    );
    CREATE INDEX IX_ChatMessages_ConversationId ON dbo.ChatMessages(ConversationId);
    PRINT N'-> [OK] Tạo bảng ChatMessages.';
END;

-- 2.8 Bảng MessageFeedback: Lưu phản hồi Like/Dislike (RLHF / LLMOps)
IF OBJECT_ID('dbo.MessageFeedback', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.MessageFeedback
    (
        Id INT IDENTITY(1,1) CONSTRAINT PK_MessageFeedback PRIMARY KEY,
        MessageId INT NOT NULL CONSTRAINT FK_MessageFeedback_ChatMessages REFERENCES dbo.ChatMessages(Id) ON DELETE CASCADE,
        Rating VARCHAR(20) NOT NULL,  -- 'positive' | 'negative'
        Comment NVARCHAR(MAX) NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_MessageFeedback_CreatedAt DEFAULT GETUTCDATE()
    );
    CREATE INDEX IX_MessageFeedback_MessageId ON dbo.MessageFeedback(MessageId);
    PRINT N'-> [OK] Tạo bảng MessageFeedback.';
END;

-- 2.9 Nâng cấp cột ParentChunkId cho Hierarchical Chunking (nếu bảng Documents đã tồn tại)
IF OBJECT_ID('dbo.Documents', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('dbo.Documents', 'ParentChunkId') IS NULL
    BEGIN
        BEGIN TRY
            ALTER TABLE dbo.Documents ADD ParentChunkId NVARCHAR(255) NULL;
            PRINT N'-> [OK] Bổ sung cột ParentChunkId vào bảng Documents.';
        END TRY
        BEGIN CATCH
            PRINT N'-> [WARN] Không thể thêm cột ParentChunkId: ' + ERROR_MESSAGE();
        END CATCH
    END
END;
GO

-------------------------------------------------------------------------------
-- 3. CẤU HÌNH FULL-TEXT SEARCH TRÊN BẢNG DOCUMENTS (NẾU HỖ TRỢ)
-------------------------------------------------------------------------------
IF SERVERPROPERTY('IsFullTextInstalled') = 1
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = 'RagFullTextCatalog')
    BEGIN
        EXEC(N'CREATE FULLTEXT CATALOG RagFullTextCatalog AS DEFAULT;');
        PRINT N'-> [OK] Tạo FullText Catalog RagFullTextCatalog.';
    END

    IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes WHERE object_id = OBJECT_ID('dbo.Documents'))
    BEGIN
        BEGIN TRY
            CREATE FULLTEXT INDEX ON dbo.Documents(document LANGUAGE 1066) -- Vietnamese
            KEY INDEX PK_Documents
            ON RagFullTextCatalog
            WITH (CHANGE_TRACKING = AUTO);
            PRINT N'-> [OK] Tạo FullText Index trên cột Documents.document.';
        END TRY
        BEGIN CATCH
            PRINT N'-> [WARN] Bỏ qua FullText Index tiếng Việt, thử tiếng Anh (1033)...';
            BEGIN TRY
                CREATE FULLTEXT INDEX ON dbo.Documents(document LANGUAGE 1033)
                KEY INDEX PK_Documents
                ON RagFullTextCatalog
                WITH (CHANGE_TRACKING = AUTO);
                PRINT N'-> [OK] Tạo FullText Index với ngôn ngữ mặc định (1033).';
            END TRY
            BEGIN CATCH
                PRINT N'-> [WARN] Không thể khởi tạo FullText Index: ' + ERROR_MESSAGE();
            END CATCH
        END CATCH
    END
END
GO

-------------------------------------------------------------------------------
-- 4. SEED DỮ LIỆU KHỞI TẠO MẪU (STANDALONE DEMO DATA)
-------------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM dbo.Conversations WHERE Id = 1)
BEGIN
    SET IDENTITY_INSERT dbo.Conversations ON;
    INSERT INTO dbo.Conversations (Id, UserId, Title, TitleSource, IsPinned, CreatedAt, UpdatedAt)
    VALUES (1, 'demo_user', N'Chào mừng bạn đến với RAG AI Service', 'system', 1, GETUTCDATE(), GETUTCDATE());
    SET IDENTITY_INSERT dbo.Conversations OFF;

    INSERT INTO dbo.ChatMessages (ConversationId, Role, Content, CreatedAt)
    VALUES (
        1,
        'assistant',
        N'Xin chào! Tôi là Trợ lý AI Thông minh (RAG Multimodal Agent). Hệ thống đã sẵn sàng hỗ trợ bạn tra cứu tài liệu, giải đáp quy trình và phân tích ảnh đính kèm. Hãy thử nạp tài liệu vào Kho tri thức hoặc đặt câu hỏi ngay!',
        GETUTCDATE()
    );
    PRINT N'-> [OK] Đã chèn dữ liệu hội thoại mẫu.';
END
GO

PRINT N'========================================================================';
PRINT N'-> HOÀN TẤT THI CÔNG KHỞI TẠO CSDL STANDALONE CHO RAG AI SERVICE!';
PRINT N'========================================================================';
