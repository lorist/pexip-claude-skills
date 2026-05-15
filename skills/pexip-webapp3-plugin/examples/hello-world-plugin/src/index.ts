import { registerPlugin } from '@pexip/plugin-api';

const PLUGIN_ID = 'hello-world';
const PLUGIN_VERSION = 1;

async function main(): Promise<void> {
  const plugin = await registerPlugin({
    id: PLUGIN_ID,
    version: PLUGIN_VERSION,
  });

  // Track which conference we joined
  let conferenceAlias = '';
  plugin.events.authenticatedWithConference.add((info) => {
    conferenceAlias = info.conferenceAlias;
    plugin.ui.showToast({ message: `Joined: ${conferenceAlias}` });
  });

  // Add a toolbar button that shows a greeting
  const btn = await plugin.ui.addButton({
    position: 'toolbar',
    label: 'Hello',
    icon: 'IconChat',
  });

  btn.onClick.add(async () => {
    plugin.ui.showToast({
      message: `Hello from ${PLUGIN_ID}! Conference: ${conferenceAlias}`,
    });
  });

  plugin.ui.showToast({ message: 'Hello World plugin loaded' });
}

main().catch((err) => console.error('[hello-world] Init failed:', err));
