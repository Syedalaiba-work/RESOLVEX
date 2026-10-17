/// Maps contract error codes to plain-language sentences shown to users.
/// Raw codes like "Error 500" are never shown in the UI.
String friendlyError(String? code, {int? status}) {
  switch (code) {
    case 'UNAUTHENTICATED':
      return 'Your email or password is not correct, or your session has ended. Please sign in again.';
    case 'FORBIDDEN':
      return 'Your account is not allowed to do this.';
    case 'NOT_FOUND':
      return 'We could not find what you were looking for.';
    case 'VALIDATION_ERROR':
      return 'Some of the details are missing or not valid. Please check and try again.';
    case 'RATE_LIMITED':
      return 'Too many requests right now. Please wait a few seconds and try again.';
    case 'NETWORK':
      return 'Cannot reach the server. Check your connection or the server address in Settings.';
    case 'TIMEOUT':
      return 'The server is taking too long to answer. Please try again.';
    // Scoring
    case 'MATCH_NOT_IN_PROGRESS':
      return 'This match is not live, so score events cannot be added.';
    case 'MATCH_NOT_FOUND':
      return 'This match no longer exists on the server.';
    case 'MATCH_EXISTS':
      return 'This match already exists.';
    case 'ILLEGAL_TRANSITION':
      return 'The match cannot move to that stage right now.';
    case 'UNKNOWN_EVENT_TYPE':
      return 'That scoring type does not exist for this sport.';
    case 'INVALID_COMPENSATION':
      return 'That event was already corrected or cannot be corrected.';
    case 'EVENT_NOT_FOUND':
      return 'The event you tried to correct was not found.';
    case 'DUPLICATE_EVENT_ID':
      return 'This event was already recorded with different details.';
    case 'INNINGS_COMPLETE':
      return 'This team\'s innings is already complete.';
    case 'SERIES_ALREADY_DECIDED':
      return 'The series is already decided.';
    case 'TIE_NOT_ALLOWED':
      return 'The match cannot end in a tie for this sport.';
    case 'INVALID_BASE_VERSION':
      return 'Your phone had newer data than the server; the server version was kept.';
    // Roster
    case 'SQUAD_FULL':
      return 'The destination squad is full.';
    case 'NOT_IN_SQUAD':
      return 'The player is no longer in that squad (someone may have moved them already).';
    case 'TRANSFER_WINDOW_CLOSED':
      return 'The transfer window is closed for that date.';
    case 'PLAYER_ON_LOAN':
      return 'The player is currently on loan and cannot be moved.';
    case 'MIN_POSITION_VIOLATION':
      return 'The squad would not have enough players in that position after the move.';
    case 'CROSS_TENANT_TRANSFER':
      return 'Players cannot be moved to a club of another organisation.';
    case 'PLAYER_NOT_FOUND':
      return 'That player was not found.';
    case 'SQUAD_NOT_FOUND':
      return 'That squad was not found.';
    case 'LEAGUE_NOT_FOUND':
      return 'That league was not found.';
    // Store
    case 'OUT_OF_STOCK':
      return 'Sorry, this item is out of stock. Your card was not charged.';
    case 'PAYMENT_DECLINED':
      return 'Your payment was declined by the bank. You were not charged.';
    case 'PAYMENT_CAPTURE_FAILED':
      return 'The payment could not be completed, so it was cancelled. You were not charged.';
    case 'INVALID_DISCOUNT_CODE':
      return 'That discount code is not valid.';
    case 'VARIANT_NOT_FOUND':
      return 'This product option is no longer available.';
    case 'DUPLICATE_ORDER_ID':
      return 'This order was already placed.';
    case 'PAYLOAD_TOO_LARGE':
      return 'The request is too large.';
  }
  if (status != null) {
    if (status == 401) return friendlyError('UNAUTHENTICATED');
    if (status == 403) return friendlyError('FORBIDDEN');
    if (status == 404) return friendlyError('NOT_FOUND');
    if (status == 429) return friendlyError('RATE_LIMITED');
    if (status >= 500) {
      return 'The server had a problem. Please try again in a moment.';
    }
  }
  return 'Something went wrong. Please try again.';
}
