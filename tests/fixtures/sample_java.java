package com.example.service;

import java.util.List;
import java.util.ArrayList;
import java.util.logging.Logger;

/**
 * Service for managing return notices.
 */
public class ReturnNoticeService {

    private static final Logger log = Logger.getLogger(ReturnNoticeService.class.getName());
    private static final int MAX_BATCH_SIZE = 100;

    private final ReturnNoticeMapper mapper;

    public ReturnNoticeService(ReturnNoticeMapper mapper) {
        this.mapper = mapper;
    }

    /**
     * Create a new return notice draft.
     */
    public ReturnNotice createDraft(CreateDraftRequest req) {
        // TODO: add validation for duplicate items
        validateRequest(req);
        ReturnNotice notice = new ReturnNotice();
        notice.setStatus(ReturnNoticeStatus.DRAFT);
        mapper.insert(notice);
        return notice;
    }

    private void validateRequest(CreateDraftRequest req) {
        if (req.getItems() == null || req.getItems().isEmpty()) {
            throw new IllegalArgumentException("Items must not be empty");
        }
    }
}
