(() => {
    const root = document.querySelector("[data-chat-app]");
    const bootstrapNode = document.getElementById("chat-bootstrap");

    if (!root || !bootstrapNode) {
        return;
    }

    const bootstrapData = JSON.parse(bootstrapNode.textContent || "{}");
    const socket = io();

    const state = {
        currentUser: bootstrapData.current_user,
        directContacts: Array.isArray(bootstrapData.direct_contacts) ? bootstrapData.direct_contacts : [],
        groupContacts: Array.isArray(bootstrapData.group_contacts) ? bootstrapData.group_contacts : [],
        availableGroupMembers: Array.isArray(bootstrapData.available_group_members)
            ? bootstrapData.available_group_members
            : [],
        initialTarget: bootstrapData.initial_target || null,
        messages: new Map(),
        active: null,
        search: "",
        selectedAttachment: null,
        typingTimer: null,
        typingVisibleTimer: null,
        typingSent: false,
        recorder: null,
        recorderStream: null,
        recorderChunks: [],
        recordingSince: null,
        recordingTicker: null,
    };

    const refs = {
        directList: document.getElementById("direct-list"),
        groupList: document.getElementById("group-list"),
        directCount: document.getElementById("direct-count"),
        groupCount: document.getElementById("group-count"),
        searchInput: document.getElementById("conversation-search"),
        chatEmpty: document.getElementById("chat-empty-state"),
        chatThread: document.getElementById("chat-thread"),
        chatMessages: document.getElementById("chat-messages"),
        activeAvatar: document.getElementById("active-chat-avatar"),
        activeName: document.getElementById("active-chat-name"),
        activeStatus: document.getElementById("active-chat-status"),
        messageInput: document.getElementById("message-input"),
        sendButton: document.getElementById("send-button"),
        emojiToggle: document.getElementById("emoji-toggle"),
        emojiPicker: document.getElementById("emoji-picker"),
        attachmentTrigger: document.getElementById("attachment-trigger"),
        attachmentInput: document.getElementById("attachment-input"),
        voiceButton: document.getElementById("voice-button"),
        composerPreview: document.getElementById("composer-preview"),
        typingIndicator: document.getElementById("typing-indicator"),
        recorderStatus: document.getElementById("recorder-status"),
        newGroupButton: document.getElementById("new-group-button"),
        changeAvatarButton: document.getElementById("change-avatar-button"),
        groupModalEl: document.getElementById("createGroupModal"),
        avatarModalEl: document.getElementById("updateAvatarModal"),
        groupNameInput: document.getElementById("group-name"),
        groupMembersList: document.getElementById("group-members-list"),
        createGroupSubmit: document.getElementById("create-group-submit"),
        avatarInput: document.getElementById("new-avatar"),
        currentAvatar: document.getElementById("current-avatar"),
        saveAvatarButton: document.getElementById("save-avatar-button"),
        currentUserAvatars: document.querySelectorAll("[data-current-user-avatar]"),
        toastStack: document.getElementById("chat-toast-stack"),
    };

    const createGroupModal = refs.groupModalEl ? new bootstrap.Modal(refs.groupModalEl) : null;
    const avatarModal = refs.avatarModalEl ? new bootstrap.Modal(refs.avatarModalEl) : null;
    const EMOJIS = [
        "😀", "😁", "😂", "🤣", "😊", "😍", "😎", "🤝", "🔥", "✨",
        "👍", "👏", "🙌", "💡", "🚀", "🎯", "❤️", "💬", "📸", "🎧",
        "😅", "😉", "🤖", "😴", "🤩", "🥳", "🙏", "👀", "💼", "🌙",
    ];

    init();

    function init() {
        renderEmojiPicker();
        renderGroupMembers();
        renderConversationLists();
        bindEvents();
        setupVoiceSupport();

        socket.on("connect", () => {
            socket.emit("join");
        });

        socket.on("new_message", handleIncomingDirectMessage);
        socket.on("new_group_message", handleIncomingGroupMessage);
        socket.on("user_typing", handleTypingEvent);
        socket.on("group_created", handleGroupCreated);
        socket.on("presence_update", handlePresenceUpdate);
        socket.on("messages_read", handleMessagesRead);

        if (state.initialTarget) {
            openConversation(state.initialTarget.type, state.initialTarget.id);
        }
    }

    function bindEvents() {
        refs.searchInput?.addEventListener("input", (event) => {
            state.search = event.target.value.trim().toLowerCase();
            renderConversationLists();
        });

        refs.messageInput?.addEventListener("input", () => {
            autoResizeTextarea();
            updateSendButtonState();
            emitTypingState(true);
        });

        refs.messageInput?.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSendMessage();
            }
        });

        refs.messageInput?.addEventListener("paste", (event) => {
            const files = Array.from(event.clipboardData?.files || []);
            if (files[0] && isSupportedAttachment(files[0])) {
                event.preventDefault();
                prepareAttachment(files[0]);
            }
        });

        refs.sendButton?.addEventListener("click", handleSendMessage);

        refs.emojiToggle?.addEventListener("click", () => {
            refs.emojiPicker?.classList.toggle("d-none");
        });

        refs.attachmentTrigger?.addEventListener("click", () => {
            refs.attachmentInput?.click();
        });

        refs.attachmentInput?.addEventListener("change", (event) => {
            const [file] = Array.from(event.target.files || []);
            if (file) {
                prepareAttachment(file);
            }
            event.target.value = "";
        });

        refs.voiceButton?.addEventListener("click", toggleVoiceRecording);

        refs.newGroupButton?.addEventListener("click", () => {
            cleanupModalArtifacts();
            refs.groupNameInput.value = "";
            refs.groupMembersList.querySelectorAll("input[type='checkbox']").forEach((input) => {
                input.checked = false;
            });
            createGroupModal?.show();
        });

        refs.createGroupSubmit?.addEventListener("click", createGroup);
        refs.changeAvatarButton?.addEventListener("click", () => {
            cleanupModalArtifacts();
            avatarModal?.show();
        });
        refs.saveAvatarButton?.addEventListener("click", updateAvatar);

        refs.avatarInput?.addEventListener("change", (event) => {
            const [file] = Array.from(event.target.files || []);
            if (!file) {
                return;
            }
            refs.currentAvatar.src = URL.createObjectURL(file);
        });

        document.addEventListener("click", (event) => {
            if (!refs.emojiPicker || refs.emojiPicker.classList.contains("d-none")) {
                return;
            }

            if (
                event.target.closest("#emoji-picker") ||
                event.target.closest("#emoji-toggle")
            ) {
                return;
            }

            refs.emojiPicker.classList.add("d-none");
        });

        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible" && state.active?.type === "direct") {
                markActiveConversationAsRead();
            }
        });

        refs.groupModalEl?.addEventListener("hidden.bs.modal", cleanupModalArtifacts);
        refs.avatarModalEl?.addEventListener("hidden.bs.modal", cleanupModalArtifacts);
    }

    function renderEmojiPicker() {
        if (!refs.emojiPicker) {
            return;
        }

        refs.emojiPicker.innerHTML = "";
        EMOJIS.forEach((emoji) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "emoji-button";
            button.textContent = emoji;
            button.addEventListener("click", () => {
                const input = refs.messageInput;
                const start = input.selectionStart || input.value.length;
                const end = input.selectionEnd || input.value.length;
                input.value = `${input.value.slice(0, start)}${emoji}${input.value.slice(end)}`;
                input.focus();
                input.selectionStart = start + emoji.length;
                input.selectionEnd = start + emoji.length;
                refs.emojiPicker.classList.add("d-none");
                autoResizeTextarea();
                updateSendButtonState();
            });
            refs.emojiPicker.appendChild(button);
        });
    }

    function renderGroupMembers() {
        if (!refs.groupMembersList) {
            return;
        }

        refs.groupMembersList.innerHTML = "";

        if (!state.availableGroupMembers.length) {
            const empty = document.createElement("div");
            empty.className = "conversation-empty";
            empty.textContent = "Guruhga qo'shish uchun boshqa foydalanuvchi topilmadi.";
            refs.groupMembersList.appendChild(empty);
            return;
        }

        state.availableGroupMembers.forEach((member) => {
            const label = document.createElement("label");
            label.className = "group-member-option";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.value = String(member.id);

            const avatar = document.createElement("img");
            avatar.src = member.avatar_url;
            avatar.alt = member.username;

            const meta = document.createElement("div");
            meta.className = "group-member-copy";

            const name = document.createElement("strong");
            name.textContent = member.username;

            const status = document.createElement("span");
            status.textContent = member.status_label || "Offline";

            meta.append(name, status);
            label.append(checkbox, avatar, meta);
            refs.groupMembersList.appendChild(label);
        });
    }

    function renderConversationLists() {
        renderConversationSection("direct", state.directContacts, refs.directList, refs.directCount);
        renderConversationSection("group", state.groupContacts, refs.groupList, refs.groupCount);
    }

    function renderConversationSection(type, items, container, counter) {
        if (!container) {
            return;
        }

        const filtered = items
            .filter((item) => {
                if (!state.search) {
                    return true;
                }
                const haystack = `${item.username || item.name} ${item.last_message_preview || ""}`.toLowerCase();
                return haystack.includes(state.search);
            })
            .sort(sortByLastActivity);

        container.innerHTML = "";
        if (counter) {
            counter.textContent = String(filtered.length);
        }

        if (!filtered.length) {
            const empty = document.createElement("div");
            empty.className = "conversation-empty";
            empty.textContent = type === "direct"
                ? "Direct suhbatlar topilmadi."
                : "Hozircha guruhlar yo'q.";
            container.appendChild(empty);
            return;
        }

        filtered.forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "conversation-item";
            if (state.active && state.active.type === type && state.active.id === item.id) {
                button.classList.add("is-active");
            }

            button.addEventListener("click", () => openConversation(type, item.id));

            const avatarWrap = document.createElement("div");
            avatarWrap.className = "conversation-avatar-wrap";

            const avatar = document.createElement("img");
            avatar.className = "conversation-avatar";
            avatar.src = item.avatar_url;
            avatar.alt = item.username || item.name;
            avatarWrap.appendChild(avatar);

            if (type === "direct" && item.status === "online") {
                const dot = document.createElement("span");
                dot.className = "conversation-online-dot";
                avatarWrap.appendChild(dot);
            }

            const copy = document.createElement("div");
            copy.className = "conversation-copy";

            const top = document.createElement("div");
            top.className = "conversation-topline";

            const title = document.createElement("strong");
            title.textContent = item.username || item.name;

            const time = document.createElement("small");
            time.textContent = formatSidebarTime(item.last_message_at);

            top.append(title, time);

            const bottom = document.createElement("div");
            bottom.className = "conversation-bottomline";

            const preview = document.createElement("span");
            preview.textContent = item.last_message_preview || "Yangi suhbat";

            bottom.appendChild(preview);

            if (type === "direct" && item.unread_count > 0) {
                const badge = document.createElement("span");
                badge.className = "conversation-badge";
                badge.textContent = String(item.unread_count);
                bottom.appendChild(badge);
            } else if (type === "group") {
                const meta = document.createElement("span");
                meta.className = "conversation-group-meta";
                meta.textContent = `${item.member_count || 0} a'zo`;
                bottom.appendChild(meta);
            }

            copy.append(top, bottom);
            button.append(avatarWrap, copy);
            container.appendChild(button);
        });
    }

    function openConversation(type, id) {
        const target = getConversationTarget(type, id);
        if (!target) {
            return;
        }

        state.active = { type, id };
        renderConversationLists();
        renderHeader(target, type);
        refs.chatEmpty.classList.add("d-none");
        refs.chatThread.classList.remove("d-none");
        refs.messageInput.disabled = false;
        refs.messageInput.focus();
        updateSendButtonState();

        if (type === "group") {
            socket.emit("join_group", { group_id: id });
        }

        const key = conversationKey(type, id);
        if (!state.messages.has(key) && target.has_history === false) {
            state.messages.set(key, []);
            renderMessages();
            if (type === "direct") {
                setDirectUnreadCount(id, 0);
                renderConversationLists();
            }
            return;
        }

        if (state.messages.has(key)) {
            renderMessages();
            if (type === "direct") {
                markActiveConversationAsRead();
            }
        }

        loadConversation(type, id);
    }

    async function loadConversation(type, id) {
        refs.chatMessages.innerHTML = `
            <div class="chat-loading">
                <span></span><span></span><span></span>
            </div>
        `;

        const endpoint = type === "direct"
            ? `/get_messages/${id}`
            : `/get_group_messages/${id}`;

        try {
            const response = await fetch(endpoint, { headers: { "X-Requested-With": "XMLHttpRequest" } });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Chat yuklanmadi.");
            }

            const key = conversationKey(type, id);
            const existing = state.messages.get(key) || [];
            const serverMessages = Array.isArray(data) ? data : [];
            const pendingMessages = existing.filter((item) => item.pending || item.failed);

            pendingMessages.forEach((pendingMessage) => {
                const alreadyPresent = serverMessages.some((message) => {
                    if (pendingMessage.client_token && message.client_token) {
                        return pendingMessage.client_token === message.client_token;
                    }
                    return pendingMessage.id === message.id;
                });

                if (!alreadyPresent) {
                    serverMessages.push(pendingMessage);
                }
            });

            state.messages.set(key, serverMessages);

            if (type === "direct") {
                setDirectUnreadCount(id, 0);
                markActiveConversationAsRead();
            }

            renderConversationLists();
            renderMessages();
        } catch (error) {
            refs.chatMessages.innerHTML = "";
            showMessageToast(error.message || "Xatolik yuz berdi.");
        }
    }

    function renderHeader(target, type) {
        refs.activeAvatar.src = target.avatar_url;
        refs.activeAvatar.alt = target.username || target.name;
        refs.activeName.textContent = target.username || target.name;
        refs.activeStatus.textContent = type === "direct"
            ? target.status_label || "Offline"
            : `${target.member_count || 0} a'zo, media yuborish yoqilgan`;
    }

    function renderMessages() {
        if (!state.active) {
            return;
        }

        const key = conversationKey(state.active.type, state.active.id);
        const items = [...(state.messages.get(key) || [])].sort(sortMessages);

        refs.chatMessages.innerHTML = "";

        if (!items.length) {
            const empty = document.createElement("div");
            empty.className = "chat-thread-empty";
            empty.textContent = "Hozircha xabar yo'q. Suhbatni shu yerdan boshlang.";
            refs.chatMessages.appendChild(empty);
            return;
        }

        items.forEach((message) => {
            refs.chatMessages.appendChild(createMessageNode(message));
        });

        scrollMessagesToBottom();
    }

    function createMessageNode(message) {
        const isGroup = state.active?.type === "group";
        const isMe = isOwnMessage(message);

        const row = document.createElement("article");
        row.className = `chat-message-row ${isMe ? "is-me" : "is-other"}`;
        row.dataset.messageId = message.id ? String(message.id) : "";
        row.dataset.clientToken = message.client_token || "";

        const avatar = document.createElement("img");
        avatar.className = "chat-message-avatar";
        avatar.alt = getAuthorName(message);
        avatar.src = getAuthorAvatar(message);

        const bubble = document.createElement("div");
        bubble.className = "chat-message-bubble";

        if (message.pending) {
            bubble.classList.add("is-pending");
        }

        if (!isMe && isGroup) {
            const label = document.createElement("strong");
            label.className = "chat-message-author";
            label.textContent = getAuthorName(message);
            bubble.appendChild(label);
        }

        if (message.content) {
            const textBlock = document.createElement("p");
            textBlock.className = "chat-message-text";
            textBlock.textContent = message.content;
            bubble.appendChild(textBlock);
        }

        renderAttachment(message, bubble);

        const meta = document.createElement("div");
        meta.className = "chat-message-meta";

        const time = document.createElement("span");
        time.textContent = formatMessageTime(message.timestamp);
        meta.appendChild(time);

        if (state.active?.type === "direct" && isMe) {
            const status = document.createElement("span");
            status.className = "chat-message-status";
            status.dataset.statusFor = message.id ? String(message.id) : message.client_token || "";
            status.textContent = message.failed
                ? "!"
                : message.pending
                    ? "..."
                    : message.is_read
                        ? "✓✓"
                        : "✓";
            meta.appendChild(status);
        }

        bubble.appendChild(meta);

        if (isMe) {
            row.append(bubble, avatar);
        } else {
            row.append(avatar, bubble);
        }

        return row;
    }

    function renderAttachment(message, bubble) {
        if (!message.file_url) {
            return;
        }

        if (message.attachment_kind === "image") {
            const link = document.createElement("a");
            link.href = message.file_url;
            link.target = "_blank";
            link.rel = "noreferrer";
            link.className = "chat-message-image-link";

            const image = document.createElement("img");
            image.src = message.file_url;
            image.alt = message.attachment_name || "Yuborilgan rasm";
            image.className = "chat-message-image";

            link.appendChild(image);
            bubble.appendChild(link);
            return;
        }

        if (message.attachment_kind === "audio") {
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "metadata";
            audio.className = "chat-message-audio";
            audio.src = message.file_url;
            bubble.appendChild(audio);
            return;
        }

        const fileLink = document.createElement("a");
        fileLink.href = message.file_url;
        fileLink.target = "_blank";
        fileLink.rel = "noreferrer";
        fileLink.className = "chat-message-file";
        fileLink.textContent = message.attachment_name || "Faylni ochish";
        bubble.appendChild(fileLink);
    }

    function prepareAttachment(file) {
        if (!isSupportedAttachment(file)) {
            showMessageToast("Faqat rasm yoki audio yuborish mumkin.");
            return;
        }

        const previewUrl = URL.createObjectURL(file);
        state.selectedAttachment = {
            file,
            kind: file.type.startsWith("audio/") ? "audio" : "image",
            previewUrl,
        };

        renderComposerPreview();
        updateSendButtonState();
    }

    function renderComposerPreview() {
        const attachment = state.selectedAttachment;

        refs.composerPreview.innerHTML = "";
        if (!attachment) {
            refs.composerPreview.classList.add("d-none");
            return;
        }

        refs.composerPreview.classList.remove("d-none");

        const label = document.createElement("div");
        label.className = "composer-preview-card";

        const close = document.createElement("button");
        close.type = "button";
        close.className = "composer-preview-remove";
        close.innerHTML = '<i class="fas fa-xmark"></i>';
        close.addEventListener("click", clearAttachment);

        const copy = document.createElement("div");
        copy.className = "composer-preview-copy";

        const title = document.createElement("strong");
        title.textContent = attachment.kind === "audio" ? "Voice / audio tayyor" : "Rasm tayyor";

        const meta = document.createElement("span");
        meta.textContent = attachment.file.name;

        copy.append(title, meta);

        label.appendChild(copy);

        if (attachment.kind === "image") {
            const image = document.createElement("img");
            image.src = attachment.previewUrl;
            image.alt = attachment.file.name;
            image.className = "composer-preview-thumb";
            label.appendChild(image);
        } else {
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.src = attachment.previewUrl;
            audio.className = "composer-preview-audio";
            label.appendChild(audio);
        }

        label.appendChild(close);
        refs.composerPreview.appendChild(label);
    }

    function clearAttachment(shouldRevoke = true) {
        if (shouldRevoke && state.selectedAttachment?.previewUrl) {
            URL.revokeObjectURL(state.selectedAttachment.previewUrl);
        }
        state.selectedAttachment = null;
        refs.composerPreview.innerHTML = "";
        refs.composerPreview.classList.add("d-none");
        updateSendButtonState();
    }

    async function handleSendMessage() {
        if (!state.active) {
            return;
        }

        const content = refs.messageInput.value.trim();
        const attachment = state.selectedAttachment;

        if (!content && !attachment) {
            return;
        }

        const clientToken = createClientToken();
        const pendingMessage = buildPendingMessage(content, attachment, clientToken);

        mergeMessageIntoState(state.active.type, state.active.id, pendingMessage);
        renderMessages();

        refs.messageInput.value = "";
        autoResizeTextarea();
        clearAttachment(false);
        updateSendButtonState();
        emitTypingState(false);

        const formData = new FormData();
        formData.append("content", content);
        formData.append("client_token", clientToken);
        if (attachment?.file) {
            formData.append("attachment", attachment.file);
        }

        const endpoint = state.active.type === "direct"
            ? `/api/conversations/direct/${state.active.id}/messages`
            : `/api/conversations/group/${state.active.id}/messages`;

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                body: formData,
            });
            const payload = await response.json();

            if (!response.ok) {
                throw new Error(payload.error || "Xabar yuborilmadi.");
            }

            reconcilePendingMessage(payload);
        } catch (error) {
            markPendingMessageFailed(clientToken);
            showMessageToast(error.message || "Xabar yuborilmadi.");
        }
    }

    function buildPendingMessage(content, attachment, clientToken) {
        const timestamp = new Date().toISOString();
        const message = {
            id: `pending-${clientToken}`,
            client_token: clientToken,
            content,
            timestamp,
            pending: true,
            is_read: false,
        };

        if (state.active.type === "direct") {
            message.sender_id = state.currentUser.id;
            message.sender_name = state.currentUser.username;
            message.sender_avatar = state.currentUser.avatar_url;
            message.receiver_id = state.active.id;
        } else {
            message.user_id = state.currentUser.id;
            message.username = state.currentUser.username;
            message.user_avatar = state.currentUser.avatar_url;
            message.group_id = state.active.id;
        }

        if (attachment) {
            message.file_url = attachment.previewUrl;
            message.attachment_kind = attachment.kind;
            message.attachment_name = attachment.file.name;
            message.attachment_mime = attachment.file.type;
        }

        return message;
    }

    function reconcilePendingMessage(message) {
        const target = inferConversationTarget(message);
        if (!target) {
            return;
        }

        const key = conversationKey(target.type, target.id);
        const items = [...(state.messages.get(key) || [])];
        const index = items.findIndex((item) => item.client_token && item.client_token === message.client_token);

        if (index >= 0) {
            const old = items[index];
            if (old.file_url && old.file_url.startsWith("blob:")) {
                URL.revokeObjectURL(old.file_url);
            }
            items[index] = { ...message, pending: false, failed: false };
        } else if (!items.some((item) => item.id === message.id)) {
            items.push(message);
        }

        state.messages.set(key, items);

        if (target.type === "direct") {
            updateDirectContactWithMessage(message);
        } else {
            updateGroupContactWithMessage(message);
        }

        if (state.active && state.active.type === target.type && state.active.id === target.id) {
            renderMessages();
            if (target.type === "direct" && message.sender_id !== state.currentUser.id) {
                markActiveConversationAsRead();
            }
        }

        renderConversationLists();
    }

    function markPendingMessageFailed(clientToken) {
        const key = state.active ? conversationKey(state.active.type, state.active.id) : null;
        if (!key) {
            return;
        }

        const items = [...(state.messages.get(key) || [])];
        const index = items.findIndex((item) => item.client_token === clientToken);
        if (index < 0) {
            return;
        }

        items[index] = { ...items[index], pending: false, failed: true };
        state.messages.set(key, items);
        renderMessages();
    }

    async function createGroup() {
        const groupName = refs.groupNameInput.value.trim();
        const memberIds = Array.from(
            refs.groupMembersList.querySelectorAll("input[type='checkbox']:checked")
        ).map((input) => Number(input.value));

        if (!groupName) {
            showMessageToast("Guruh nomini kiriting.");
            return;
        }

        try {
            const response = await fetch("/create_group", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    group_name: groupName,
                    member_ids: memberIds,
                }),
            });

            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.error || "Guruh yaratilmadi.");
            }

            upsertGroupContact(payload.group);
            renderConversationLists();
            createGroupModal?.hide();
            socket.emit("join_group", { group_id: payload.group.id });
            openConversation("group", payload.group.id);
        } catch (error) {
            showMessageToast(error.message || "Guruh yaratilmadi.");
        }
    }

    async function updateAvatar() {
        const [file] = Array.from(refs.avatarInput.files || []);
        if (!file) {
            showMessageToast("Avatar uchun rasm tanlang.");
            return;
        }

        const formData = new FormData();
        formData.append("avatar", file);

        try {
            const response = await fetch("/update_avatar", {
                method: "POST",
                body: formData,
            });
            const payload = await response.json();

            if (!response.ok) {
                throw new Error(payload.error || "Avatar yangilanmadi.");
            }

            state.currentUser.avatar_url = payload.avatar_url;
            refs.currentUserAvatars.forEach((avatar) => {
                avatar.src = payload.avatar_url;
            });
            refs.currentAvatar.src = payload.avatar_url;
            avatarModal?.hide();
        } catch (error) {
            showMessageToast(error.message || "Avatar yangilanmadi.");
        }
    }

    function handleIncomingDirectMessage(message) {
        reconcilePendingMessage(message);
    }

    function handleIncomingGroupMessage(message) {
        reconcilePendingMessage(message);
    }

    function handleGroupCreated(group) {
        upsertGroupContact(group);
        renderConversationLists();
    }

    function handlePresenceUpdate(payload) {
        const contact = state.directContacts.find((item) => item.id === payload.user_id);
        if (!contact) {
            return;
        }

        contact.status = payload.status;
        contact.status_label = payload.status_label;
        renderConversationLists();

        if (state.active?.type === "direct" && state.active.id === payload.user_id) {
            renderHeader(contact, "direct");
        }
    }

    function handleMessagesRead(payload) {
        if (!state.active || state.active.type !== "direct" || state.active.id !== payload.user_id) {
            return;
        }

        const key = conversationKey("direct", payload.user_id);
        const items = [...(state.messages.get(key) || [])];
        let changed = false;

        items.forEach((item) => {
            if (payload.message_ids.includes(item.id)) {
                item.is_read = true;
                changed = true;
            }
        });

        if (changed) {
            state.messages.set(key, items);
            renderMessages();
        }
    }

    function handleTypingEvent(payload) {
        if (
            !state.active ||
            state.active.type !== "direct" ||
            state.active.id !== payload.user_id
        ) {
            return;
        }

        if (payload.is_typing) {
            refs.typingIndicator.textContent = `${payload.username} yozmoqda...`;
            clearTimeout(state.typingVisibleTimer);
            state.typingVisibleTimer = window.setTimeout(() => {
                refs.typingIndicator.textContent = "";
            }, 2000);
            return;
        }

        refs.typingIndicator.textContent = "";
    }

    function emitTypingState(isTyping) {
        if (!state.active || state.active.type !== "direct") {
            return;
        }

        const hasText = refs.messageInput.value.trim().length > 0;
        const nextState = isTyping && hasText;

        if (state.typingSent !== nextState) {
            socket.emit("typing", {
                receiver_id: state.active.id,
                is_typing: nextState,
            });
            state.typingSent = nextState;
        }

        clearTimeout(state.typingTimer);
        state.typingTimer = window.setTimeout(() => {
            if (state.typingSent) {
                socket.emit("typing", {
                    receiver_id: state.active.id,
                    is_typing: false,
                });
                state.typingSent = false;
            }
        }, 1200);
    }

    async function markActiveConversationAsRead() {
        if (!state.active || state.active.type !== "direct") {
            return;
        }

        setDirectUnreadCount(state.active.id, 0);
        renderConversationLists();

        try {
            await fetch(`/api/conversations/direct/${state.active.id}/read`, {
                method: "POST",
            });
        } catch (error) {
            // Read sync failure should not block the UI.
        }
    }

    function updateSendButtonState() {
        const canSend = Boolean(
            state.active &&
            !state.recorder &&
            (refs.messageInput.value.trim() || state.selectedAttachment)
        );
        refs.sendButton.disabled = !canSend;
    }

    function autoResizeTextarea() {
        if (!refs.messageInput) {
            return;
        }

        refs.messageInput.style.height = "auto";
        refs.messageInput.style.height = `${Math.min(refs.messageInput.scrollHeight, 160)}px`;
    }

    function scrollMessagesToBottom() {
        refs.chatMessages.scrollTop = refs.chatMessages.scrollHeight;
    }

    function setupVoiceSupport() {
        if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
            refs.voiceButton.disabled = true;
            refs.recorderStatus.textContent = "Voice note bu brauzerda yo'q";
            return;
        }

        refs.recorderStatus.textContent = "Voice note tayyor";
    }

    async function toggleVoiceRecording() {
        if (state.recorder) {
            stopRecording(false);
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            state.recorderStream = stream;
            state.recorderChunks = [];
            state.recorder = new MediaRecorder(stream);
            state.recordingSince = Date.now();

            state.recorder.addEventListener("dataavailable", (event) => {
                if (event.data.size > 0) {
                    state.recorderChunks.push(event.data);
                }
            });

            state.recorder.addEventListener("stop", () => {
                const blob = new Blob(state.recorderChunks, {
                    type: state.recorder.mimeType || "audio/webm",
                });
                if (blob.size > 0) {
                    const file = new File([blob], `voice-${Date.now()}.webm`, {
                        type: blob.type || "audio/webm",
                    });
                    prepareAttachment(file);
                }
                cleanupRecorder();
            });

            state.recorder.start();
            refs.voiceButton.classList.add("is-recording");
            refs.recorderStatus.textContent = "Yozilmoqda... 00:00";
            state.recordingTicker = window.setInterval(updateRecordingClock, 500);
            updateSendButtonState();
        } catch (error) {
            showMessageToast("Mikrofon ruxsati berilmadi.");
        }
    }

    function stopRecording(discard) {
        if (!state.recorder) {
            return;
        }

        if (discard) {
            state.recorderChunks = [];
        }

        state.recorder.stop();
    }

    function cleanupRecorder() {
        if (state.recordingTicker) {
            clearInterval(state.recordingTicker);
        }
        refs.voiceButton.classList.remove("is-recording");
        refs.recorderStatus.textContent = "Voice note tayyor";

        if (state.recorderStream) {
            state.recorderStream.getTracks().forEach((track) => track.stop());
        }

        state.recorder = null;
        state.recorderStream = null;
        state.recorderChunks = [];
        state.recordingSince = null;
        state.recordingTicker = null;
        updateSendButtonState();
    }

    function updateRecordingClock() {
        if (!state.recordingSince) {
            return;
        }
        const seconds = Math.floor((Date.now() - state.recordingSince) / 1000);
        const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
        const remainder = String(seconds % 60).padStart(2, "0");
        refs.recorderStatus.textContent = `Yozilmoqda... ${minutes}:${remainder}`;
    }

    function updateDirectContactWithMessage(message) {
        const otherId = message.sender_id === state.currentUser.id
            ? message.receiver_id
            : message.sender_id;

        let contact = state.directContacts.find((item) => item.id === otherId);
        if (!contact) {
            contact = {
                id: otherId,
                username: message.sender_id === state.currentUser.id
                    ? message.receiver_name || "User"
                    : message.sender_name || "User",
                avatar_url: message.sender_id === state.currentUser.id
                    ? message.receiver_avatar || state.currentUser.avatar_url
                    : message.sender_avatar,
                status: "offline",
                status_label: "Offline",
                unread_count: 0,
            };
            state.directContacts.push(contact);
        }

        contact.last_message_preview = buildPreviewFromMessage(message);
        contact.last_message_at = message.timestamp;

        const isIncoming = message.sender_id !== state.currentUser.id;
        const isActiveConversation = state.active?.type === "direct" && state.active.id === otherId;
        contact.unread_count = isIncoming && !isActiveConversation
            ? (contact.unread_count || 0) + 1
            : 0;
    }

    function updateGroupContactWithMessage(message) {
        let group = state.groupContacts.find((item) => item.id === message.group_id);
        if (!group) {
            group = {
                id: message.group_id,
                name: "Yangi guruh",
                avatar_url: "/static/avatars/group.svg",
                member_count: 0,
            };
            state.groupContacts.push(group);
        }

        group.last_message_preview = buildPreviewFromMessage(message);
        group.last_message_at = message.timestamp;
    }

    function upsertGroupContact(group) {
        const existing = state.groupContacts.find((item) => item.id === group.id);
        if (existing) {
            Object.assign(existing, group);
        } else {
            state.groupContacts.push(group);
        }
    }

    function setDirectUnreadCount(userId, value) {
        const contact = state.directContacts.find((item) => item.id === userId);
        if (contact) {
            contact.unread_count = value;
        }
    }

    function mergeMessageIntoState(type, id, message) {
        const key = conversationKey(type, id);
        const items = [...(state.messages.get(key) || [])];
        const existingIndex = items.findIndex((item) => {
            if (message.client_token && item.client_token === message.client_token) {
                return true;
            }
            return message.id && item.id === message.id;
        });

        if (existingIndex >= 0) {
            items[existingIndex] = { ...items[existingIndex], ...message };
        } else {
            items.push(message);
        }

        state.messages.set(key, items);

        if (type === "direct") {
            updateDirectContactWithMessage(message);
        } else {
            updateGroupContactWithMessage(message);
        }

        renderConversationLists();
    }

    function inferConversationTarget(message) {
        if (typeof message.group_id !== "undefined") {
            return { type: "group", id: Number(message.group_id) };
        }

        if (typeof message.sender_id !== "undefined") {
            const otherId = message.sender_id === state.currentUser.id
                ? message.receiver_id
                : message.sender_id;
            return { type: "direct", id: Number(otherId) };
        }

        return null;
    }

    function getConversationTarget(type, id) {
        if (type === "direct") {
            return state.directContacts.find((item) => item.id === id) || null;
        }
        return state.groupContacts.find((item) => item.id === id) || null;
    }

    function getAuthorName(message) {
        return message.sender_name || message.username || "User";
    }

    function getAuthorAvatar(message) {
        return message.sender_avatar || message.user_avatar || state.currentUser.avatar_url;
    }

    function isOwnMessage(message) {
        return (message.sender_id || message.user_id) === state.currentUser.id;
    }

    function isSupportedAttachment(file) {
        return file.type.startsWith("image/") || file.type.startsWith("audio/");
    }

    function buildPreviewFromMessage(message) {
        const prefix = isOwnMessage(message) ? "Siz: " : "";
        if (message.content) {
            return `${prefix}${message.content.slice(0, 42)}`;
        }
        if (message.attachment_kind === "audio") {
            return `${prefix}Audio yuborildi`;
        }
        if (message.attachment_kind === "image") {
            return `${prefix}Rasm yuborildi`;
        }
        return `${prefix}Media yuborildi`;
    }

    function conversationKey(type, id) {
        return `${type}:${id}`;
    }

    function createClientToken() {
        if (window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
        return `token-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

    function cleanupModalArtifacts() {
        if (document.querySelector(".modal.show")) {
            return;
        }

        document.body.classList.remove("modal-open");
        document.body.style.removeProperty("overflow");
        document.body.style.removeProperty("padding-right");
        document.querySelectorAll(".modal-backdrop").forEach((backdrop) => backdrop.remove());
    }

    function sortByLastActivity(a, b) {
        const aTime = new Date(a.last_message_at || a.created_at || 0).getTime();
        const bTime = new Date(b.last_message_at || b.created_at || 0).getTime();
        return bTime - aTime;
    }

    function sortMessages(a, b) {
        const timeDiff = new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime();
        if (timeDiff !== 0) {
            return timeDiff;
        }
        const aId = Number.isFinite(Number(a.id)) ? Number(a.id) : 0;
        const bId = Number.isFinite(Number(b.id)) ? Number(b.id) : 0;
        return aId - bId;
    }

    function formatSidebarTime(value) {
        if (!value) {
            return "";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "";
        }
        return new Intl.DateTimeFormat("uz-UZ", {
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    function formatMessageTime(value) {
        if (!value) {
            return "";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "";
        }
        return new Intl.DateTimeFormat("uz-UZ", {
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    function showMessageToast(message) {
        if (!refs.toastStack) {
            window.alert(message);
            return;
        }

        const toast = document.createElement("div");
        toast.className = "chat-toast";
        toast.textContent = message;
        refs.toastStack.appendChild(toast);

        window.setTimeout(() => {
            toast.classList.add("is-visible");
        }, 10);

        window.setTimeout(() => {
            toast.classList.remove("is-visible");
            window.setTimeout(() => toast.remove(), 220);
        }, 2800);
    }
})();
