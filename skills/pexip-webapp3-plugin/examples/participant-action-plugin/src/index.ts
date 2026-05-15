import { registerPlugin, type ParticipantID } from '@pexip/plugin-api';

const PLUGIN_ID = 'participant-action';
const PLUGIN_VERSION = 1;

async function main(): Promise<void> {
  const plugin = await registerPlugin({
    id: PLUGIN_ID,
    version: PLUGIN_VERSION,
  });

  // Track participants: UUID → display name
  const nameMap = new Map<string, string>();

  // Add a participant action button (appears in participant context menu)
  const btn = await plugin.ui.addButton({
    position: 'participantActions',
    label: 'Toggle Role',
  });

  // Update button visibility based on participant list
  plugin.events.participants.add(({ participants }) => {
    nameMap.clear();
    const eligible: ParticipantID[] = [];

    for (const p of participants) {
      nameMap.set(p.uuid as string, p.displayName);
      if (!p.isWaiting) {
        eligible.push(p.uuid);
      }
    }

    // Only show the button for admitted participants
    btn.update({
      position: 'participantActions',
      label: 'Toggle Role',
      participantIDs: eligible,
    });
  });

  // Handle button click
  // IMPORTANT: destructure { participantUuid } — onClick receives an object,
  // not a bare string. Using (participantUuid) => gives the whole object.
  btn.onClick.add(async ({ participantUuid }) => {
    const name = nameMap.get(participantUuid as string) || 'Participant';

    // Fetch current role via RPC
    // IMPORTANT: resp.data.result (not resp.result) due to response wrapping
    const resp = await plugin.conference.requestParticipants({});
    const participants = resp.data.result;

    // RPC uses snake_case: display_name, not displayName
    const target = participants.find(
      (p: any) => p.uuid === participantUuid
    );

    if (!target) {
      plugin.ui.showToast({ message: `${name} not found`, isDanger: true });
      return;
    }

    // RPC role is "chair"/"guest"; setRole uses "host"/"guest"
    const currentRole = target.role === 'chair' ? 'host' : 'guest';
    const newRole = currentRole === 'host' ? 'guest' : 'host';

    await plugin.conference.setRole({
      participantUuid,
      role: newRole,
    });

    plugin.ui.showToast({
      message: `${name}: ${currentRole} → ${newRole}`,
    });
  });

  plugin.ui.showToast({ message: 'Participant Action plugin loaded' });
}

main().catch((err) => console.error('[participant-action] Init failed:', err));
