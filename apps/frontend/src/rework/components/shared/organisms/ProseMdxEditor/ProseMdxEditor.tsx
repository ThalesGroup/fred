// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// The prose subset of MDXEditor's plugins and toolbar shared by every markdown
// surface in the app (the team wiki and the writable-document capability).
// Each caller still owns its own <MDXEditor>: this only removes the duplicated
// plugin list and button row, not the editor's lifecycle or state.
//
// `markdownShortcutPlugin` is deliberately not included here — callers that add
// their own extra plugins (e.g. code blocks) append it themselves, last, to
// keep it after every registered plugin as MDXEditor expects.

import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  CreateLink,
  headingsPlugin,
  InsertTable,
  linkDialogPlugin,
  linkPlugin,
  listsPlugin,
  ListsToggle,
  quotePlugin,
  Separator,
  tablePlugin,
  thematicBreakPlugin,
  UndoRedo,
} from "@mdxeditor/editor";

export function proseMdxPlugins() {
  return [
    headingsPlugin(),
    listsPlugin(),
    quotePlugin(),
    linkPlugin(),
    linkDialogPlugin(),
    thematicBreakPlugin(),
    tablePlugin(),
  ];
}

export function ProseToolbarButtons() {
  return (
    <>
      <UndoRedo />
      <Separator />
      <BoldItalicUnderlineToggles />
      <Separator />
      <BlockTypeSelect />
      <Separator />
      <ListsToggle />
      <Separator />
      <CreateLink />
      <Separator />
      <InsertTable />
    </>
  );
}
