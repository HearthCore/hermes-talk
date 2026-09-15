import * as HermesSDK from '@hermes/plugin-sdk'
import * as React from 'react'

const TALK_CSS = __HERMES_TALK_CSS__;
const DESKTOP_API = '/api/plugins/hermes-talk';
const h = React.createElement;
let desktopContext = null;
const desktopOpeners = new Set();

function ownerKey(owner) {
  return JSON.stringify([owner?.connectionId, owner?.profile,
    owner?.sessionId ?? null, owner?.storedSessionId ?? null]);
}

export function desktopAvailability(controller) {
  if (!controller || controller.capabilities?.microphoneLease !== 1 ||
      controller.capabilities?.pinnedRest !== 1 || controller.capabilities?.prepareSession !== 1) {
    return 'Update Hermes Desktop to use Talk in this conversation.';
  }
  if (typeof controller.acquire !== 'function' ||
      typeof controller.owner?.connectionId !== 'string' || !controller.owner.connectionId ||
      typeof controller.owner?.profile !== 'string' || !controller.owner.profile) {
    return 'Open a connected Hermes conversation before starting Talk.';
  }
  return '';
}

export function createDesktopTalkSDK(context, controller, onPreparing = () => {}) {
  const currentController = typeof controller === 'function' ? controller : () => controller;
  const unavailable = desktopAvailability(currentController());
  if (unavailable) throw new Error(unavailable);
  let owner = Object.freeze({ ...currentController().owner });
  const scope = Object.freeze({ connectionId: owner.connectionId, profile: owner.profile });
  const sdk = {
    React,
    hooks: React,
    components: { Button: HermesSDK.Button, Input: HermesSDK.Input },
    managedAuthentication: true,
    get desktopOwner() { return owner; },
    async prepareTask({ tabId, signal }) {
      const current = currentController();
      const original = owner;
      if (ownerKey(current?.owner) !== ownerKey(original) || signal?.aborted) {
        throw new Error('The Hermes conversation changed. Reopen Talk in the selected conversation.');
      }
      if (current.capabilities?.prepareSession !== 1 || typeof current.prepareSession !== 'function') {
        throw new Error('Update Hermes Desktop to start Talk in this conversation.');
      }
      let prepared = null;
      onPreparing(true);
      try {
        prepared = await current.prepareSession();
        if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
        if (!prepared?.storedSessionId || prepared.connectionId !== scope.connectionId ||
            prepared.profile !== scope.profile || (original.storedSessionId &&
              prepared.storedSessionId !== original.storedSessionId)) {
          throw new Error('The Hermes conversation changed. Reopen Talk in the selected conversation.');
        }
        // React must publish the prepared owner before its current lease can be used.
        const deadline = Date.now() + 1000;
        while (ownerKey(currentController()?.owner) !== ownerKey(prepared) && Date.now() < deadline) {
          if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
          await new Promise(resolve => window.setTimeout(resolve, 10));
        }
        if (ownerKey(currentController()?.owner) !== ownerKey(prepared)) {
          throw new Error('The Hermes conversation changed. Reopen Talk in the selected conversation.');
        }
        owner = Object.freeze({ ...prepared });
        const response = await sdk.fetchJSON(DESKTOP_API + '/targets', {
          method: 'POST', signal,
          body: JSON.stringify({ peer_id: 'local', profile: owner.profile,
            session_id: owner.storedSessionId, tab_id: tabId }),
        });
        if (signal?.aborted || ownerKey(currentController()?.owner) !== ownerKey(owner)) {
          throw new DOMException('Request cancelled', 'AbortError');
        }
        const matches = (response?.ok && Array.isArray(response.targets) ? response.targets : [])
          .filter(target => target.peer_id === 'local' && target.profile === owner.profile &&
            target.session_id === owner.storedSessionId);
        if (matches.length !== 1) throw new Error('The current conversation is unavailable. Reopen it and try again.');
        return matches[0];
      } finally {
        onPreparing(false, owner);
      }
    },
    validateVoiceMode(status) {
      if (!status || !['live', 'native'].includes(status.voiceMode)) {
        throw new Error('Desktop Talk supports GPT-Live and OpenAI Realtime. ' +
          'Use the dashboard for cascade audio. Your voice settings have not been changed.');
      }
    },
    async acquireMicrophone({ signal } = {}) {
      const current = currentController();
      if (desktopAvailability(current) || ownerKey(current.owner) !== ownerKey(owner)) {
        throw new Error('The Hermes conversation changed. Reopen Talk in the selected conversation.');
      }
      const lease = await current.acquire({ signal });
      if (!lease || typeof lease.release !== 'function' || !lease.signal) {
        lease?.release?.();
        throw new Error('Hermes could not grant microphone ownership. Stop its other voice session first.');
      }
      return lease;
    },
    async fetchJSON(path, options = {}, timeoutMs) {
      if (!path.startsWith(DESKTOP_API + '/')) {
        throw new Error('Talk attempted to access a different plugin route.');
      }
      if (options.signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
      const suffix = path.slice(DESKTOP_API.length);
      const headers = new Headers(options.headers || {});
      // Keep in-flight receipts on their captured owner, including a late /close.
      // The shared UI's generation checks retire results after navigation.
      try {
        return await context.rest(suffix, {
          method: options.method,
          body: typeof options.body === 'string' ? JSON.parse(options.body) : options.body,
          timeoutMs: timeoutMs || 30000,
          scope,
          pluginToken: headers.get('x-talk-token') || undefined,
        });
      } catch (error) {
        const prefix = "Error invoking remote method 'hermes:api': Error: ";
        if (typeof error?.message === 'string' && error.message.startsWith(prefix)) {
          throw new Error(error.message.slice(prefix.length));
        }
        throw error;
      }
    },
  };
  return sdk;
}

function DesktopTalkPresentation(props) {
  const { active, starting, error, needsToken, popoverOpen, onPopoverOpenChange, stopTalk } = props;
  const previous = React.useRef({ active: false, starting: false, error: '', needsToken: false });
  React.useEffect(() => {
    const before = previous.current;
    previous.current = { active, starting, error, needsToken };
    const failed = Boolean(error || needsToken);
    if (failed && (error !== before.error || needsToken !== before.needsToken ||
        (before.starting && !starting && !active))) {
      onPopoverOpenChange(true);
    } else if (active && !before.active) {
      onPopoverOpenChange(false);
    }
  }, [active, starting, error, needsToken, onPopoverOpenChange]);

  return h(React.Fragment, null,
    (active || starting) && h('span', {
      style: { display: 'inline-flex', alignItems: 'center', gap: '0.375rem' },
    },
    h('span', { role: 'status', 'aria-live': 'polite', style: { fontSize: '0.75rem' } },
      active ? 'Connected' : 'Connecting…'),
    h(HermesSDK.Button, {
      type: 'button', variant: 'ghost', size: 'sm',
      'aria-label': starting ? 'Cancel Talk connection' : 'Stop talking', onClick: stopTalk,
    }, starting ? 'Cancel' : 'Stop')),
    popoverOpen && h(HermesSDK.PopoverContent, {
      side: 'top', align: 'end', 'aria-label': 'Hermes Talk',
      style: { width: 'min(360px, calc(100vw - 24px))', maxHeight: '70vh',
        overflowY: 'auto', padding: '1rem' },
      onSubmit: event => event.stopPropagation(),
    }, h(DesktopTalkView, props)));
}

function DesktopTalkPanel({ context, controller, onPreparing, presentationProps }) {
  const controllerRef = React.useRef(controller);
  controllerRef.current = controller;
  const surface = React.useMemo(() => createTalkSurface(
    createDesktopTalkSDK(context, () => controllerRef.current, onPreparing)), [context]);
  return h(React.Fragment, null,
    h('style', null, TALK_CSS),
    h(surface.TalkPage, { presentation: DesktopTalkPresentation, presentationProps }));
}

export function openFocusedTalk() {
  const state = HermesSDK.host?.state;
  const focused = state?.focusedSessionOwner?.get();
  const stored = state?.focusedStoredSessionId?.get() || null;
  const runtime = state?.focusedSessionId?.get() || null;
  const matches = [...desktopOpeners].filter(entry => {
    const candidate = entry.owner();
    return focused && candidate?.connectionId === focused.connectionId &&
      candidate?.profile === focused.profile && (candidate?.storedSessionId || null) === stored &&
      (stored || (candidate?.sessionId || null) === runtime);
  });
  if (matches.length === 1) matches[0].open();
  else HermesSDK.host?.notify('Open a connected conversation, then choose Talk beside its message box.');
}

function DesktopTalkAction() {
  const useController = HermesSDK.useComposerVoiceController || (() => null);
  const controller = useController();
  const [attached, setAttached] = React.useState(null);
  const [popoverOpen, setPopoverOpen] = React.useState(false);
  const controllerRef = React.useRef(controller);
  controllerRef.current = controller;
  const preparingRef = React.useRef(false);
  const currentOwner = ownerKey(controller?.owner);
  const unavailable = desktopAvailability(controller);
  const attachedHere = attached !== null &&
    (attached.expectedKey === currentOwner || preparingRef.current);
  const openPanel = () => {
    const key = ownerKey(controllerRef.current?.owner);
    setAttached(previous => previous && (previous.expectedKey === key || preparingRef.current)
      ? previous : { initialKey: key, expectedKey: key });
    setPopoverOpen(true);
  };
  const onPopoverOpenChange = value => {
    if (value) openPanel();
    else setPopoverOpen(false);
  };
  React.useEffect(() => {
    const entry = { owner: () => controllerRef.current?.owner, open: openPanel };
    desktopOpeners.add(entry);
    return () => desktopOpeners.delete(entry);
  }, []);
  React.useEffect(() => {
    if (attached && attached.expectedKey !== currentOwner && !preparingRef.current) {
      setAttached(null);
      setPopoverOpen(false);
    }
  }, [currentOwner, attached]);
  const onPreparing = (value, nextOwner) => {
    preparingRef.current = value;
    if (!value) {
      const expectedKey = ownerKey(nextOwner);
      setAttached(previous => previous && expectedKey === ownerKey(controllerRef.current?.owner)
        ? { ...previous, expectedKey } : null);
    }
  };

  return h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '0.25rem' } },
    h(HermesSDK.Popover, {
      modal: false, open: popoverOpen && attachedHere, onOpenChange: onPopoverOpenChange,
    },
    h(HermesSDK.PopoverTrigger, { asChild: true },
      h(HermesSDK.Button, {
        type: 'button', variant: 'ghost', size: 'sm', title: 'Open Hermes Talk',
        'aria-label': 'Open Hermes Talk',
      }, 'Talk')),
    attachedHere && (unavailable || !desktopContext
      ? popoverOpen && h(HermesSDK.PopoverContent, {
        side: 'top', align: 'end', 'aria-label': 'Hermes Talk',
        style: { width: 'min(360px, calc(100vw - 24px))' },
      }, h('p', { role: 'status' }, unavailable || 'The Talk plugin is not ready.'))
      : h(DesktopTalkPanel, {
        key: attached.initialKey, context: desktopContext, controller, onPreparing,
        presentationProps: { popoverOpen, onPopoverOpenChange },
      }))));
}

export default {
  id: 'hermes-talk',
  name: 'Hermes Talk',
  description: 'GPT-Live subscription or explicit API voice, with Hermes task delegation.',
  register(context) {
    desktopContext = context;
    context.register({
      id: 'talk', area: 'composer.actions', order: 45,
      render: () => h(DesktopTalkAction),
    });
    context.register({
      id: 'talk-topbar', area: 'titleBar.tools.right', order: 45,
      data: { id: 'hermes-talk', label: 'Talk', title: 'Talk to Hermes',
        icon: h(HermesSDK.Codicon, { name: 'mic' }), onSelect: openFocusedTalk },
    });
    context.onDispose(() => {
      if (desktopContext === context) desktopContext = null;
    });
  },
};
