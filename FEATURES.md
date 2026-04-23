# Features Documentation

## 🔄 Track Update/Replace Feature

### Overview
When a mentor has already submitted track selections and runs `/mentor-track` again, the system now intelligently asks them whether they want to **update** (add new tracks) or **replace** (discard old tracks and use the new selection).

### Use Cases

#### Scenario 1: Mentor wants to add more expertise areas
- Initial submission: `frontend`, `backend`
- Run `/mentor-track` again and select: `devops`
- System asks: "Update or Replace?"
- Choose **Update** → Result: `backend`, `devops`, `frontend`

#### Scenario 2: Mentor changes their mind completely
- Initial submission: `frontend`, `backend`
- Run `/mentor-track` again and select: `devops`, `mobile`
- System asks: "Update or Replace?"
- Choose **Replace** → Result: `devops`, `mobile`

### How It Works

```
┌─────────────────────────────────────────────────────────┐
│ Mentor runs /mentor-track                               │
└─────────┬───────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│ System checks: Does this mentor exist in the sheet?     │
└─────────┬───────────────────────────────────────────────┘
          │
          ├─ NO  ─────────────► Save directly ─────┐
          │                                          │
          └─ YES ─────────────┐                     │
                              ▼                     │
                ┌──────────────────────────┐        │
                │ Show confirmation dialog │        │
                │ [Add] [Replace]          │        │
                └──────────┬───────────────┘        │
                           │                        │
                 ┌─────────┴─────────┐              │
                 ▼                   ▼              │
            [ADD buttons]    [REPLACE button]      │
                 │                   │              │
                 ▼                   ▼              │
            Merge tracks       Use new only        │
            (deduplicate,      only                │
             alphabetize)                           │
                 │                   │              │
                 └─────────┬─────────┘              │
                           ▼                       │
                ┌──────────────────────────┐       │
                │ Save to Google Sheet     │◄──────┘
                └──────────┬───────────────┘
                           │
                           ▼
                ┌──────────────────────────┐
                │ Send DM confirmation     │
                │ Sync to all stages       │
                │ Notify admin channel     │
                └──────────────────────────┘
```

### User-Facing Experience

#### Initial Form
```
Please select the track(s) you would like to mentor:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Select all tracks you're interested in:
[dropdown showing: Frontend, Backend, DevOps, Mobile, etc.]

[Submit Selection]
```

#### Confirmation Dialog (if mentor already submitted)
```
🔄 You've already submitted tracks before!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your current tracks:
Frontend, Backend

New selection:
DevOps

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What would you like to do?

[📝 Update (Add new tracks)]  [🔄 Replace (Use only new)]
```

#### After Choosing "Update"
```
✅ Track selection updated!
Your tracks have been added to: Backend, DevOps, Frontend

(DM received)
✅ Your track selection has been updated (tracks added).

All your tracks: Backend, DevOps, Frontend

🚀 You will be added to all stage channels for these 
tracks! Thank you for mentoring with HNG!
```

#### After Choosing "Replace"
```
✅ Track selection updated!
Your tracks have been changed to: DevOps

(DM received)
✅ Your track selection has been changed.

Selected Tracks: DevOps

🚀 You will be added to all stage channels for these 
tracks! Thank you for mentoring with HNG!
```

### Technical Implementation

#### Key Functions Added/Modified

**mentor_track_cli.py**
- `get_mentor_existing_tracks(user_id: str) -> List[str]` - Retrieves mentor's current tracks

**server/main.py**
- `_process_submission(user_id, payload)` - Enhanced to check if mentor exists
- `_show_update_confirmation_dialog(user_id, existing_tracks, new_tracks, payload)` - Shows dialog
- `_handle_update_confirmation(user_id, action_type)` - Processes "add" or "replace"
- `_save_tracks_and_notify(user_id, tracks, payload, is_update)` - Extracted save logic
- `_process_action(action_id, payload)` - Updated to handle confirmation button clicks

#### Data Flow

1. **Check Mentor Exists**: Query Google Sheet for mentor's Slack ID
2. **Get Existing Tracks**: Parse "Selected Tracks" column from existing record
3. **Show Dialog**: Post confirmation dialog with two buttons
4. **Store Pending Update**: Save request data to `_process_submission.pending_updates` dict
5. **Handle Confirmation**: 
   - **ADD**: `combined = list(set(existing + new))` then sort
   - **REPLACE**: Use `new_tracks` directly
6. **Save and Notify**: Update sheet, send DMs, sync to stage channels

#### Error Handling
- Graceful handling when pending_updates dict is empty
- Fallback if mentor info can't be retrieved
- Proper logging at each step for debugging

### Testing

The feature includes a comprehensive test suite (`test_update_replace.py`) that validates:
1. ✅ Track merging logic (ADD with deduplication)
2. ✅ Track replacement logic  
3. ✅ Overlapping tracks handling
4. ✅ Dialog structure and button configuration
5. ✅ DM message formatting for both actions

All tests pass successfully.

### Deployment Notes

- No database schema changes required
- No new environment variables needed
- Backward compatible with existing track submissions
- Existing mentors can update their selections without issues

### Future Enhancements

- [ ] Add audit trail for track changes in spreadsheet (add a "Changes" column)
- [ ] Allow mentors to preview what mentoring groups they'll join
- [ ] Add analytics dashboard for mentor track selections
- [ ] Implement rate limiting for rapid re-submissions
