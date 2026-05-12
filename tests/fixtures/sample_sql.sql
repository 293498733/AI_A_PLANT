-- Create return notice table
CREATE TABLE return_notice (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    notice_no VARCHAR(32) NOT NULL COMMENT '通知单号',
    status TINYINT DEFAULT 0 COMMENT '状态: 0草稿 2已提交 3已出库 9已取消',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_notice_no (notice_no),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='返修通知单';

-- Insert dictionary data
INSERT INTO sys_dict_data (dict_type, dict_value, dict_label)
VALUES ('return_notice_status', '0', '草稿');

-- Query pending notices
SELECT id, notice_no, status
FROM return_notice
WHERE status IN (0, 2)
ORDER BY create_time DESC;
