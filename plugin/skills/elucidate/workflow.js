export const meta = {
  name: 'elucidate',
  description: 'Spawn one agent per prompt the build wrote, each reading its prompt and writing its return',
  phases: [{ title: 'Spawn', detail: 'one agent per prompt, in parallel' }],
}

function task(one) {
  return [
    `Read exactly one file with the Read tool: ${one.path}. It states everything you are given and everything you are asked, including the path to write to and the shape to write.`,
    `Do exactly what it says: write the JSON result to ${one.out} with the Write tool, then return it. Read nothing else. Do not narrate.`,
  ].join('\n')
}

const results = await parallel(args.prompts.map(one => () =>
  agent(task(one), { label: one.label, phase: 'Spawn', schema: args.shapes[one.schema], model: one.model, effort: one.effort })))

return {
  spawned: args.prompts.length,
  returned: results.filter(Boolean).length,
  failed: args.prompts.filter((one, at) => !results[at]).map(one => one.label),
}
