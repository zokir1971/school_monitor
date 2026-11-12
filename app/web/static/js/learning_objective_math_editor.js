document.addEventListener(
  "DOMContentLoaded",
  () => {

    // ===================================================
    // DIALOG
    // ===================================================

    const dialog =
      document.getElementById(
        "qb-math-dialog"
      );

    const mathField =
      document.getElementById(
        "qb-math-field"
      );

    if (!dialog || !mathField) {
      return;
    }

    const saveButton =
      dialog.querySelector(
        "[data-math-dialog-save]"
      );

    const cancelButton =
      dialog.querySelector(
        "[data-math-dialog-cancel]"
      );

    const closeButton =
      dialog.querySelector(
        "[data-math-dialog-close]"
      );


    // ===================================================
    // STATE
    // ===================================================

    let activeEditor = null;
    let formulaAnswerTarget = null;

    let editingMathNode = null;

    let savedRange = null;


    /*
     * Внутренний clipboard формул.
     *
     * Здесь хранится чистый LaTeX:
     *
     * x_{1,2}=\frac{-3\pm\sqrt{17}}{4}
     *
     * а НЕ:
     *
     * $$ ... $$
     *
     * Поэтому копирование между A/B/C/D
     * не превращает формулу в обычный текст.
     */
    let copiedMathLatex = null;


    /*
     * Для каждого rich-editor храним
     * собственную последнюю позицию курсора.
     */
    const editorRanges =
      new WeakMap();


    // ===================================================
    // BASIC HELPERS
    // ===================================================

    function getContent(
      editor
    ) {
      return editor.querySelector(
        "[data-rich-content]"
      );
    }


    function getSegmentsInput(
      editor
    ) {
      return editor.querySelector(
        "[data-rich-segments]"
      );
    }


    function getPlainInput(
      editor
    ) {
      return editor.querySelector(
        "[data-rich-plain-value]"
      );
    }


    function getSelectedMathNode(
      editor
    ) {
      return editor.querySelector(
        "[data-rich-math].is-selected"
      );
    }


    // ===================================================
    // DIALOG
    // ===================================================

    // MathLive's keyboard is attached to body, outside this modal.
    // Reserve its height so the panel and the keyboard never overlap.
    let keyboard = null;
    function updateKeyboardSpace() {
      const height = !dialog.hidden && keyboard?.visible
        ? Math.ceil(keyboard.boundingRect?.height || 0) : 0;
      dialog.style.setProperty("--lo-keyboard-height", `${height}px`);
    }
    customElements.whenDefined("math-field").then(() => {
      keyboard = window.mathVirtualKeyboard || null;
      keyboard?.addEventListener("geometrychange", updateKeyboardSpace);
      updateKeyboardSpace();
    });
    window.addEventListener("resize", updateKeyboardSpace);

    function showMathDialog() {
      dialog.hidden = false;

      document.body.classList.add(
        "qb-math-dialog-open"
      );

      window.requestAnimationFrame(
        () => {
          if (!dialog.hidden) {
            mathField.focus();
            updateKeyboardSpace();
          }
        }
      );
    }


    function hideMathDialog() {
      keyboard?.hide();
      mathField.blur();
      dialog.hidden = true;
      updateKeyboardSpace();

      document.body.classList.remove(
        "qb-math-dialog-open"
      );
    }


    function closeMathDialog() {
      hideMathDialog();

      activeEditor = null;
      formulaAnswerTarget = null;

      editingMathNode = null;
    }


    // ===================================================
    // MATH TOOL BUTTONS
    // ===================================================

    function flashMathToolButton(
      button
    ) {
      button.classList.add(
        "is-active"
      );

      window.setTimeout(
        () => {
          button.classList.remove(
            "is-active"
          );
        },
        180
      );
    }


    function insertMathCommand(
      command
    ) {
      if (!command) {
        return;
      }

      mathField.focus();

      mathField.insert(
        command,
        {
          insertionMode:
            "replaceSelection",
        }
      );

      mathField.focus();
    }


    function insertMathAction(
      action
    ) {
      if (!action) {
        return;
      }

      mathField.focus();


      // -----------------------------------------------
      // LOWER INDEX
      // -----------------------------------------------

      if (action === "subscript") {

        mathField.insert(
          "_{}",
          {
            insertionMode:
              "replaceSelection",
          }
        );

        /*
         * После вставки:
         *
         * _{}
         *
         * курсор MathLive обычно находится
         * после конструкции.
         *
         * Перемещаем его внутрь индекса.
         */
        mathField.executeCommand(
          "moveToPreviousChar"
        );

        mathField.focus();

        return;
      }


      // -----------------------------------------------
      // FRACTION
      // -----------------------------------------------

      if (action === "fraction") {

        mathField.executeCommand(
          [
            "insert",
            "\\frac{#0}{#1}",
          ]
        );

        mathField.focus();

        return;
      }
    }


    function initMathTools() {

      dialog
        .querySelectorAll(
          "[data-math-insert]"
        )
        .forEach(
          (button) => {

            button.addEventListener(
              "click",
              () => {

                const command =
                  button.dataset.mathInsert;

                if (!command) {
                  return;
                }

                flashMathToolButton(
                  button
                );

                insertMathCommand(
                  command
                );
              }
            );

          }
        );


      dialog
        .querySelectorAll(
          "[data-math-action]"
        )
        .forEach(
          (button) => {

            button.addEventListener(
              "click",
              () => {

                const action =
                  button.dataset.mathAction;

                if (!action) {
                  return;
                }

                flashMathToolButton(
                  button
                );

                insertMathAction(
                  action
                );
              }
            );

          }
        );
    }


    // ===================================================
    // RANGE HELPERS
    // ===================================================

    function rangeBelongsToContent(
      range,
      content
    ) {
      if (!range || !content) {
        return false;
      }

      const node =
        range.commonAncestorContainer;

      return (
        node === content
        ||
        content.contains(node)
      );
    }


    function createRangeAtEnd(
      content
    ) {
      const range =
        document.createRange();

      range.selectNodeContents(
        content
      );

      range.collapse(false);

      return range;
    }


    function saveSelection(
      content
    ) {
      const selection =
        window.getSelection();

      if (
        !selection
        ||
        selection.rangeCount === 0
      ) {
        return;
      }

      const range =
        selection.getRangeAt(0);

      if (
        !rangeBelongsToContent(
          range,
          content
        )
      ) {
        return;
      }

      const clonedRange =
        range.cloneRange();

      editorRanges.set(
        content,
        clonedRange
      );

      savedRange =
        clonedRange.cloneRange();
    }


    function restoreSelection(
      content
    ) {
      const selection =
        window.getSelection();

      if (!selection) {
        return null;
      }

      let range =
        editorRanges.get(
          content
        );

      if (!range) {
        range =
          savedRange;
      }


      if (
        !rangeBelongsToContent(
          range,
          content
        )
      ) {
        range =
          createRangeAtEnd(
            content
          );
      } else {
        range =
          range.cloneRange();
      }


      selection.removeAllRanges();

      selection.addRange(
        range
      );


      editorRanges.set(
        content,
        range.cloneRange()
      );

      savedRange =
        range.cloneRange();


      return range;
    }


    function focusAtSavedSelection(content) {
      // focus fires the editor's focus handler synchronously. Capture first.
      const stored = editorRanges.get(content) || savedRange;
      const range = rangeBelongsToContent(stored, content)
        ? stored.cloneRange() : createRangeAtEnd(content);
      content.focus({preventScroll: true});
      editorRanges.set(content, range);
      savedRange = range.cloneRange();
      return restoreSelection(content);
    }

    function placeCaretAfter(
      node
    ) {
      const content =
        (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement)
          ?.closest("[data-rich-content]");

      if (!content) {
        return;
      }

      const selection =
        window.getSelection();

      if (!selection) {
        return;
      }

      const range =
        document.createRange();

      range.setStartAfter(
        node
      );

      range.collapse(true);


      selection.removeAllRanges();

      selection.addRange(
        range
      );


      editorRanges.set(
        content,
        range.cloneRange()
      );

      savedRange =
        range.cloneRange();
    }


    // ===================================================
    // NORMALIZE CONTENT
    // ===================================================

    function normalizeEditor(
      content
    ) {
      // Keep text nodes stable: live Range endpoints must not be merged away.

      const children =
        Array.from(
          content.childNodes
        );


      children.forEach(
        (node) => {

          /*
           * В rich-editor разрешаем:
           *
           * 1. обычные TEXT_NODE;
           * 2. наши span[data-rich-math].
           *
           * Любой случайный HTML превращаем
           * обратно в простой текст.
           */
          if (
            node.nodeType ===
              Node.ELEMENT_NODE
            &&
            !node.matches(
              "[data-rich-math], [data-rich-image]"
            )
          ) {
            const textNode =
              document.createTextNode(
                node.tagName === "BR" ? "\n" : (node.textContent || "")
              );

            node.replaceWith(
              textNode
            );
          }

        }
      );


      // Keep text nodes stable: live Range endpoints must not be merged away.
    }


    // ===================================================
    // DOM -> SEGMENTS
    // ===================================================

    function validMediaKey(key) {
      return typeof key === "string" && /^question-bank\/media\/[1-9][0-9]*\/[0-9a-f]{32}\.(png|jpg|webp)$/.test(key);
    }

    function createImageNode(segment, editor) {
      if (!validMediaKey(segment.object_key)) throw new Error("Invalid image key");
      const node = document.createElement("span");
      node.dataset.richImage = "";
      node.dataset.objectKey = segment.object_key;
      node.dataset.alt = segment.alt || "";
      node.contentEditable = "false";
      node.style.cssText = "display:inline-block;max-width:100%;margin:8px 0;vertical-align:middle";
      const img = document.createElement("img");
      const url = new URL(editor.dataset.mediaViewUrl, window.location.href);
      url.searchParams.set("object_key", segment.object_key);
      img.src = url.href;
      img.alt = segment.alt || "";
      img.style.cssText = "display:block;max-width:100%;max-height:360px;height:auto";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = window.SchoolMonitorI18n.t("ed_b4ec9ff0c0b8");
      remove.addEventListener("click", () => { node.remove(); syncEditor(editor); });
      node.append(img, remove);
      return node;
    }

    function collectSegments(
  content
) {
  normalizeEditor(
    content
  );

  const segments = [];


  content.childNodes.forEach(
    (node) => {

      // ===============================================
      // TEXT
      // ===============================================

      if (
        node.nodeType ===
          Node.TEXT_NODE
      ) {
        const text =
          node.textContent || "";


        /*
         * Пустой текстовый DOM-узел
         * вообще не превращаем в segment.
         *
         * Это защищает backend от:
         *
         * {
         *   type: "text",
         *   text: ""
         * }
         */
        if (
          text.length === 0
        ) {
          return;
        }


        const previous =
          segments[
            segments.length - 1
          ];


        /*
         * Если предыдущий segment тоже text,
         * объединяем их.
         */
        if (
          previous
          &&
          previous.type === "text"
        ) {
          previous.text += text;
        } else {
          segments.push({
            type: "text",
            text: text,
          });
        }


        return;
      }


      if (node.nodeType === Node.ELEMENT_NODE && node.matches("[data-rich-image]")) {
        segments.push({type: "image", object_key: node.dataset.objectKey, alt: node.dataset.alt || ""});
        return;
      }

      // ===============================================
      // LATEX
      // ===============================================

      if (
        node.nodeType ===
          Node.ELEMENT_NODE
        &&
        node.matches(
          "[data-rich-math]"
        )
      ) {
        const latex =
          String(
            node.dataset.latex || ""
          ).trim();


        /*
         * Пустую формулу тоже не сохраняем.
         */
        if (!latex) {
          return;
        }


        segments.push({
          type: "latex",
          text: latex,
        });
      }

    }
  );


  /*
   * Финальная страховка.
   *
   * Ни один segment с пустым text
   * не должен уйти на backend.
   */
  return segments.filter(
    (segment) => {

      return (
        segment.type === "image" || typeof segment.text ===
          "string"
        &&
        segment.text.length > 0
      );

    }
  );
}

    // ===================================================
    // SYNC HIDDEN INPUTS
    // ===================================================

    function syncEditor(
      editor
    ) {
      const content =
        getContent(
          editor
        );

      const segmentsInput =
        getSegmentsInput(
          editor
        );

      const plainInput =
        getPlainInput(
          editor
        );


      if (
        !content
        ||
        !segmentsInput
        ||
        !plainInput
      ) {
        return;
      }


      const segments =
        collectSegments(
          content
        );


      if (
        segments.length === 0
      ) {
        segmentsInput.value = "";

        plainInput.value = "";
        editor.dispatchEvent(new CustomEvent('objective:rich-sync', {detail: []}));
        return;
      }


      // -----------------------------------------------
      // REAL RICH CONTRACT
      // -----------------------------------------------

      segmentsInput.value = JSON.stringify(segments);
      editor.dispatchEvent(new CustomEvent('objective:rich-sync', {detail: segments}));


      // -----------------------------------------------
      // PLAIN FALLBACK
      // -----------------------------------------------

      plainInput.value =
        segments
          .map(
            (segment) => {

              if (
                segment.type === "text"
              ) {
                return segment.text;
              }

              return segment.type === "image" ? "[Сурет]" : "$$" + segment.text + "$$";
            }
          )
          .join("")
          .trim();
    }


    // ===================================================
    // CREATE FORMULA NODE
    // ===================================================

    function createMathNode(
      latex
    ) {
      const node =
        document.createElement(
          "span"
        );


      node.className =
        "qb-rich-math";


      node.dataset.richMath = "";

      node.dataset.latex =
        latex;


      /*
       * Формула является единым atomic-элементом.
       * Пользователь не редактирует внутренний
       * math-field прямо внутри contenteditable.
       */
      node.contentEditable =
        "false";


      /*
       * Формулу можно сфокусировать клавиатурой.
       */
      node.tabIndex = 0;


      node.setAttribute(
        "role",
        "button"
      );

      node.setAttribute(
        "aria-label",
        window.SchoolMonitorI18n.t("ed_efe34c19b42b")
      );

      node.setAttribute(
        "aria-pressed",
        "false"
      );


      const field =
        document.createElement(
          "math-field"
        );


      field.className =
        "qb-rich-math__field";


      field.readOnly = true;

      field.value =
        latex;


      field.setAttribute(
        "read-only",
        ""
      );


      node.appendChild(
        field
      );

      // Read-only MathLive can consume pointer events inside its shadow DOM.
      // A transparent sibling covers the preview and delegates clicks to the
      // atomic formula wrapper; LaTeX remains on the wrapper, unchanged.
      const hitbox = document.createElement("span");
      hitbox.className = "qb-rich-math__hitbox";
      hitbox.setAttribute("aria-hidden", "true");
      node.appendChild(hitbox);

      node.addEventListener("pointerdown", event => {
        event.preventDefault();
        node.focus({preventScroll: true});
        const editor = node.closest("[data-rich-editor]");
        if (editor) selectMathNode(editor, node);
      });
      node.addEventListener("focus", () => {
        const editor = node.closest("[data-rich-editor]");
        if (editor) selectMathNode(editor, node);
      });

      return node;
    }


    // ===================================================
    // FORMULA SELECTION
    // ===================================================

    function clearMathSelection(
      editor
    ) {
      editor
        .querySelectorAll(
          "[data-rich-math].is-selected"
        )
        .forEach(
          (node) => {

            node.classList.remove(
              "is-selected"
            );

            node.setAttribute(
              "aria-pressed",
              "false"
            );

          }
        );


      updateEditorToolbar(
        editor
      );
    }


    function clearSelectionsExcept(
      currentEditor
    ) {
      document
        .querySelectorAll(
          "[data-rich-editor]"
        )
        .forEach(
          (editor) => {

            if (
              editor === currentEditor
            ) {
              return;
            }

            clearMathSelection(
              editor
            );

          }
        );
    }


    function selectMathNode(
      editor,
      mathNode
    ) {
      if (!mathNode) {
        return;
      }


      clearSelectionsExcept(
        editor
      );


      /*
       * В одном редакторе выбираем
       * только одну формулу.
       */
      editor
        .querySelectorAll(
          "[data-rich-math].is-selected"
        )
        .forEach(
          (node) => {

            if (
              node === mathNode
            ) {
              return;
            }

            node.classList.remove(
              "is-selected"
            );

            node.setAttribute(
              "aria-pressed",
              "false"
            );

          }
        );


      mathNode.classList.add(
        "is-selected"
      );


      mathNode.setAttribute(
        "aria-pressed",
        "true"
      );


      updateEditorToolbar(
        editor
      );
    }


    // ===================================================
    // TOOLBAR STATE
    // ===================================================

    function updateEditorToolbar(
      editor
    ) {
      const selectedMath =
        getSelectedMathNode(
          editor
        );


      const editButton =
        editor.querySelector(
          "[data-rich-edit-math]"
        );

      const copyButton =
        editor.querySelector(
          "[data-rich-copy-math]"
        );

      const pasteButton =
        editor.querySelector(
          "[data-rich-paste-math]"
        );

      const deleteButton =
        editor.querySelector(
          "[data-rich-delete-math]"
        );


      const hasSelectedMath =
        Boolean(
          selectedMath
        );


      /*
       * Өңдеу / Көшіру / Жою
       * требуют выбранную формулу.
       */

      if (editButton) {
        editButton.disabled =
          !hasSelectedMath;
      }


      if (copyButton) {
        copyButton.disabled =
          !hasSelectedMath;
      }


      if (deleteButton) {
        deleteButton.disabled =
          !hasSelectedMath;
      }


      /*
       * Қою не зависит от выбора формулы.
       *
       * После первого Көшіру кнопка становится
       * доступна во всех редакторах.
       */

      if (pasteButton) {
        pasteButton.disabled =
          !copiedMathLatex;
      }
    }


    function updateAllToolbars() {
      document
        .querySelectorAll(
          "[data-rich-editor]"
        )
        .forEach(
          (editor) => {
            updateEditorToolbar(
              editor
            );
          }
        );
    }


    // ===================================================
    // OPEN NEW FORMULA
    // ===================================================

    function openNewFormula(
      editor
    ) {
      const content =
        getContent(
          editor
        );

      if (!content) {
        return;
      }


      activeEditor =
        editor;


      editingMathNode =
        null;


      const range =
        editorRanges.get(
          content
        );


      if (
        range
        &&
        rangeBelongsToContent(
          range,
          content
        )
      ) {
        savedRange =
          range.cloneRange();
      } else {
        savedRange =
          createRangeAtEnd(
            content
          );
      }


      mathField.value = "";


      showMathDialog();
    }


    // ===================================================
    // OPEN EXISTING FORMULA
    // ===================================================

    function openExistingFormula(
      editor,
      mathNode
    ) {
      if (!mathNode) {
        return;
      }


      activeEditor =
        editor;


      editingMathNode =
        mathNode;


      selectMathNode(
        editor,
        mathNode
      );


      mathField.value =
        mathNode.dataset.latex || "";


      showMathDialog();
    }


    // ===================================================
    // SAVE FORMULA
    // ===================================================

    function saveFormula() {
      if (formulaAnswerTarget) {
        const latex = String(mathField.value || '').trim();
        if (!latex) return;
        const input = formulaAnswerTarget.querySelector('[data-formula-answer-input]');
        input.value = latex;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        closeMathDialog();
        input.focus();
        return;
      }
      if (!activeEditor) {
        return;
      }


      const latex =
        String(
          mathField.value || ""
        ).trim();


      if (!latex) {
        return;
      }


      const editor =
        activeEditor;


      const content =
        getContent(
          editor
        );


      if (!content) {
        return;
      }


      // -----------------------------------------------
      // UPDATE EXISTING
      // -----------------------------------------------

      if (editingMathNode) {

        editingMathNode.dataset.latex =
          latex;


        const field =
          editingMathNode.querySelector(
            "math-field"
          );


        if (field) {
          field.value =
            latex;
        }


        selectMathNode(
          editor,
          editingMathNode
        );


        placeCaretAfter(
          editingMathNode
        );

      }

      // -----------------------------------------------
      // INSERT NEW
      // -----------------------------------------------

      else {

        focusAtSavedSelection(content);


        restoreSelection(
          content
        );


        const selection =
          window.getSelection();


        if (
          !selection
          ||
          selection.rangeCount === 0
        ) {
          return;
        }


        const range =
          selection.getRangeAt(0);


        range.deleteContents();


        const mathNode =
          createMathNode(
            latex
          );


        range.insertNode(
          mathNode
        );


        selectMathNode(
          editor,
          mathNode
        );


        placeCaretAfter(
          mathNode
        );
      }


      syncEditor(
        editor
      );


      hideMathDialog();


      activeEditor = null;

      editingMathNode = null;
    }


    // ===================================================
    // COPY FORMULA
    // ===================================================

    function copySelectedFormula(
      editor
    ) {
      const mathNode =
        getSelectedMathNode(
          editor
        );


      if (!mathNode) {
        return;
      }


      const latex =
        String(
          mathNode.dataset.latex || ""
        ).trim();


      if (!latex) {
        return;
      }


      /*
       * Копируем именно чистый LaTeX.
       */
      copiedMathLatex =
        latex;


      /*
       * После этого Қою становится
       * доступной во всех A/B/C/D.
       */
      updateAllToolbars();
    }


    // ===================================================
    // PASTE FORMULA
    // ===================================================

    function pasteCopiedFormula(
      editor
    ) {
      if (!copiedMathLatex) {
        return;
      }


      const content =
        getContent(
          editor
        );


      if (!content) {
        return;
      }


      focusAtSavedSelection(content);


      restoreSelection(
        content
      );


      const selection =
        window.getSelection();


      if (
        !selection
        ||
        selection.rangeCount === 0
      ) {
        return;
      }


      const range =
        selection.getRangeAt(0);


      range.deleteContents();


      /*
       * Создаём новый полноценный
       * latex-сегмент.
       *
       * Не вставляем строку:
       *
       * $$ formula $$
       */
      const mathNode =
        createMathNode(
          copiedMathLatex
        );


      range.insertNode(
        mathNode
      );


      selectMathNode(
        editor,
        mathNode
      );


      placeCaretAfter(
        mathNode
      );


      syncEditor(
        editor
      );
    }


    // ===================================================
    // DELETE FORMULA
    // ===================================================

    function deleteMathNode(
      editor,
      mathNode
    ) {
      if (!mathNode) {
        return;
      }


      const content =
        getContent(
          editor
        );


      if (!content) {
        return;
      }


      const previous =
        mathNode.previousSibling;


      const next =
        mathNode.nextSibling;


      mathNode.remove();


      // Keep text nodes stable: live Range endpoints must not be merged away.


      syncEditor(
        editor
      );


      updateEditorToolbar(
        editor
      );


      const selection =
        window.getSelection();


      if (!selection) {
        return;
      }


      const range =
        document.createRange();


      // -----------------------------------------------
      // PREVIOUS TEXT
      // -----------------------------------------------

      if (
        previous
        &&
        previous.isConnected
        &&
        previous.nodeType ===
          Node.TEXT_NODE
      ) {

        range.setStart(
          previous,
          previous.textContent.length
        );

        range.collapse(true);

      }

      // -----------------------------------------------
      // NEXT NODE
      // -----------------------------------------------

      else if (
        next
        &&
        next.isConnected
      ) {

        range.setStartBefore(
          next
        );

        range.collapse(true);

      }

      // -----------------------------------------------
      // END
      // -----------------------------------------------

      else {

        range.selectNodeContents(
          content
        );

        range.collapse(false);
      }


      selection.removeAllRanges();

      selection.addRange(
        range
      );


      editorRanges.set(
        content,
        range.cloneRange()
      );


      savedRange =
        range.cloneRange();
    }


    function deleteSelectedFormula(
      editor
    ) {
      const mathNode =
        getSelectedMathNode(
          editor
        );


      if (!mathNode) {
        return;
      }


      deleteMathNode(
        editor,
        mathNode
      );
    }


    // ===================================================
    // PLAIN TEXT PASTE
    // ===================================================

    function insertPlainText(
      editor,
      text
    ) {
      if (!text) {
        return;
      }


      const content =
        getContent(
          editor
        );


      if (!content) {
        return;
      }


      let selection =
        window.getSelection();


      if (
        !selection
        ||
        selection.rangeCount === 0
        ||
        !rangeBelongsToContent(
          selection.getRangeAt(0),
          content
        )
      ) {

        restoreSelection(
          content
        );


        selection =
          window.getSelection();
      }


      if (
        !selection
        ||
        selection.rangeCount === 0
      ) {
        return;
      }


      const range =
        selection.getRangeAt(0);


      range.deleteContents();


      const textNode =
        document.createTextNode(
          text
        );


      range.insertNode(
        textNode
      );


      placeCaretAfter(
        textNode
      );


      syncEditor(
        editor
      );
    }


    // ===================================================
    // INIT ONE RICH EDITOR
    // ===================================================

    function initEditor(
      editor
    ) {
      const content =
        getContent(
          editor
        );


      const addMathButton =
        editor.querySelector(
          "[data-rich-add-math]"
        );


      const editButton =
        editor.querySelector(
          "[data-rich-edit-math]"
        );


      const copyButton =
        editor.querySelector(
          "[data-rich-copy-math]"
        );


      const pasteButton =
        editor.querySelector(
          "[data-rich-paste-math]"
        );


      const deleteButton =
        editor.querySelector(
          "[data-rich-delete-math]"
        );


      if (
        !content
        ||
        !addMathButton
      ) {
        return;
      }


      const imageButton = editor.querySelector("[data-rich-add-image]");
      const imageInput = editor.querySelector("[data-rich-image-file]");
      const mediaStatus = editor.querySelector("[data-rich-media-status]");
      if (imageButton && imageInput) {
        let pending = false;
        imageButton.addEventListener("mousedown", () => saveSelection(content));
        imageButton.addEventListener("click", () => imageInput.click());
        editor.closest("form")?.addEventListener("submit", event => {
          if (pending) { event.preventDefault(); mediaStatus.textContent = window.SchoolMonitorI18n.t("ed_1fb562b6a5d8"); }
        });
        imageInput.addEventListener("change", async () => {
          const file = imageInput.files[0];
          if (!file) return;
          pending = true;
          imageButton.disabled = true;
          mediaStatus.textContent = window.SchoolMonitorI18n.t("ed_cfa4d64a32e9");
          try {
            if (file.size > 5 * 1024 * 1024) throw new Error(window.SchoolMonitorI18n.t("ed_19ba77e2e46f"));
            const body = new FormData();
            body.append("file", file);
            const response = await fetch(editor.dataset.mediaUploadUrl, {method: "POST", body, credentials: "same-origin"});
            if (!response.headers.get("content-type")?.includes("application/json")) throw new Error(window.SchoolMonitorI18n.t("ed_59c98f413669"));
            const result = await response.json();
            if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : window.SchoolMonitorI18n.t("ed_7ab627a6a2e6"));
            const node = createImageNode(result, editor);
            focusAtSavedSelection(content);
            const range = restoreSelection(content);
            if (!range) throw new Error(window.SchoolMonitorI18n.t("ed_801919f46e4b"));
            range.deleteContents();
            range.insertNode(node);
            range.setStartAfter(node);
            range.collapse(true);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
            saveSelection(content);
            syncEditor(editor);
            mediaStatus.textContent = "";
          } catch (error) { mediaStatus.textContent = error.message; }
          finally { pending = false; imageButton.disabled = false; imageInput.value = ""; }
        });
      }

      // Restore initial rich content before the editor's first sync.
      if (editor.hasAttribute("data-initial-segments")) {
        try {
          const segments = JSON.parse(editor.dataset.initialSegments || "[]");
          if (!Array.isArray(segments) || segments.some(s =>
              !s || !["text", "latex", "image"].includes(s.type) || (s.type === "image" ? !validMediaKey(s.object_key) : typeof s.text !== "string"))) {
            throw new Error("Invalid initial segments");
          }
          content.replaceChildren();
          for (const segment of segments) {
            content.appendChild(segment.type === "latex"
              ? createMathNode(segment.text)
              : segment.type === "image" ? createImageNode(segment, editor) : document.createTextNode(segment.text));
          }
        } catch (error) {
          console.error("Rich editor hydration failed", error);
          const form = editor.closest("form");
          if (form) {
            const message = document.createElement("div");
            message.className = "qb-empty";
            message.textContent = window.SchoolMonitorI18n.t("ed_8c602d30e0b6");
            form.prepend(message);
            form.querySelectorAll('[type="submit"]').forEach(button => button.disabled = true);
            form.addEventListener("submit", event => event.preventDefault());
          }
          return;
        }
      }

      content.style.whiteSpace = "pre-wrap";
      const lineButton = document.createElement("button");
      lineButton.type = "button";
      lineButton.textContent = window.SchoolMonitorI18n.t("ed_8510e7687e54");
      lineButton.dataset.richNewline = "";
      lineButton.addEventListener("pointerdown", event => {
        saveSelection(content);
        if (event.pointerType === "mouse") event.preventDefault();
      });
      lineButton.addEventListener("click", () => {
        focusAtSavedSelection(content);
        insertPlainText(editor, "\n");
      });
      editor.querySelector(".lo-rich-tools")?.append(lineButton);
      content.addEventListener("beforeinput", event => {
        if (["insertParagraph", "insertLineBreak"].includes(event.inputType)) {
          event.preventDefault();
          saveSelection(content);
          insertPlainText(editor, "\n");
        }
      });

      // =================================================
      // INITIAL RANGE
      // =================================================

      editorRanges.set(
        content,
        createRangeAtEnd(
          content
        )
      );


      // =================================================
      // CARET EVENTS
      // =================================================

      [
        "keyup",
        "mouseup",
        "focus",
        "touchend",
      ].forEach(
        (eventName) => {

          content.addEventListener(
            eventName,
            () => {
              saveSelection(
                content
              );
            }
          );

        }
      );


      // =================================================
      // INPUT
      // =================================================

      content.addEventListener(
        "input",
        () => {

          syncEditor(
            editor
          );


          saveSelection(
            content
          );

        }
      );


      // =================================================
      // CLICK / TAP FORMULA
      // =================================================

      content.addEventListener(
        "click",
        (event) => {

          const mathNode =
            event.target.closest?.(
              "[data-rich-math]"
            );


          if (!mathNode) {
            return;
          }


          event.preventDefault();


          selectMathNode(
            editor,
            mathNode
          );

        }
      );


      // =================================================
      // DOUBLE CLICK = EDIT
      // =================================================

      content.addEventListener(
        "dblclick",
        (event) => {

          const mathNode =
            event.target.closest?.(
              "[data-rich-math]"
            );


          if (!mathNode) {
            return;
          }


          event.preventDefault();


          openExistingFormula(
            editor,
            mathNode
          );

        }
      );


      // =================================================
      // + FORMULA
      // =================================================

      addMathButton.addEventListener(
        "pointerdown",
        (event) => {

          /*
           * Не позволяем мыши украсть caret.
           *
           * На touch сохранённый range уже
           * находится в editorRanges.
           */
          if (
            event.pointerType === "mouse"
          ) {
            event.preventDefault();
          }


          saveSelection(
            content
          );

        }
      );


      addMathButton.addEventListener(
        "click",
        () => {

          openNewFormula(
            editor
          );

        }
      );


      // =================================================
      // EDIT
      // =================================================

      editButton?.addEventListener(
        "click",
        () => {

          const mathNode =
            getSelectedMathNode(
              editor
            );


          if (!mathNode) {
            return;
          }


          openExistingFormula(
            editor,
            mathNode
          );

        }
      );


      // =================================================
      // COPY
      // =================================================

      copyButton?.addEventListener(
        "click",
        () => {

          copySelectedFormula(
            editor
          );

        }
      );


      // =================================================
      // PASTE BUTTON
      // =================================================

      pasteButton?.addEventListener(
        "pointerdown",
        (event) => {

          if (
            event.pointerType === "mouse"
          ) {
            event.preventDefault();
          }


          saveSelection(
            content
          );

        }
      );


      pasteButton?.addEventListener(
        "click",
        () => {

          pasteCopiedFormula(
            editor
          );

        }
      );


      // =================================================
      // DELETE BUTTON
      // =================================================

      deleteButton?.addEventListener(
        "click",
        () => {

          deleteSelectedFormula(
            editor
          );

        }
      );


      // =================================================
      // KEYBOARD
      // =================================================

      content.addEventListener(
        "keydown",
        (event) => {

          if (event.key === "Enter" && !event.target.closest?.("[data-rich-math]")) {
            event.preventDefault();
            saveSelection(content);
            insertPlainText(editor, "\n");
            return;
          }

          const mathNode =
            event.target.closest?.(
              "[data-rich-math]"
            );


          // ---------------------------------------------
          // FORMULA HAS FOCUS
          // ---------------------------------------------

          if (mathNode) {

            // ENTER / SPACE -> EDIT

            if (
              event.key === "Enter"
              ||
              event.key === " "
            ) {

              event.preventDefault();


              selectMathNode(
                editor,
                mathNode
              );


              openExistingFormula(
                editor,
                mathNode
              );


              return;
            }


            // DELETE

            if (
              event.key === "Delete"
              ||
              event.key === "Backspace"
            ) {

              event.preventDefault();


              deleteMathNode(
                editor,
                mathNode
              );


              return;
            }


            // CTRL/CMD + C

            if (
              (
                event.ctrlKey
                ||
                event.metaKey
              )
              &&
              event.key.toLowerCase() === "c"
            ) {

              event.preventDefault();


              selectMathNode(
                editor,
                mathNode
              );


              copySelectedFormula(
                editor
              );


              return;
            }
          }


          // ---------------------------------------------
          // CTRL/CMD + V
          // ---------------------------------------------

          if (
            (
              event.ctrlKey
              ||
              event.metaKey
            )
            &&
            event.key.toLowerCase() === "v"
            &&
            copiedMathLatex
          ) {

            event.preventDefault();


            saveSelection(
              content
            );


            pasteCopiedFormula(
              editor
            );

          }

        }
      );


      // =================================================
      // SYSTEM PASTE
      // =================================================

      content.addEventListener(
        "paste",
        (event) => {

          /*
           * Обычный системный clipboard
           * всегда вставляем как plain text.
           *
           * Формулы между нашими полями
           * копируются кнопками:
           *
           * Көшіру -> Қою
           */
          event.preventDefault();


          const text =
            event.clipboardData
              ?.getData(
                "text/plain"
              )
            || "";


          insertPlainText(
            editor,
            text
          );

        }
      );


      // =================================================
      // INITIAL SYNC
      // =================================================

      syncEditor(
        editor
      );


      updateEditorToolbar(
        editor
      );
    }


    // ===================================================
    // INITIALIZE MATH TOOLS
    // ===================================================

    initMathTools();
    window.ObjectiveRichEditor = {init: initEditor, sync: syncEditor};


    // ===================================================
    // INITIALIZE ALL RICH EDITORS
    // ===================================================

    document
      .querySelectorAll(
        "[data-rich-editor]"
      )
      .forEach(
        (editor) => {

          initEditor(
            editor
          );

        }
      );


    updateAllToolbars();


    // ===================================================
    // SAVE DIALOG
    // ===================================================

    saveButton?.addEventListener(
      "click",
      () => {

        saveFormula();

      }
    );


    // ===================================================
    // CANCEL DIALOG
    // ===================================================

    cancelButton?.addEventListener(
      "click",
      () => {

        closeMathDialog();

      }
    );


    // ===================================================
    // CLOSE DIALOG
    // ===================================================

    closeButton?.addEventListener(
      "click",
      () => {

        closeMathDialog();

      }
    );


    // ===================================================
    // ESCAPE
    // ===================================================

    document.addEventListener(
      "keydown",
      (event) => {

        if (
          event.key !== "Escape"
          ||
          dialog.hidden
        ) {
          return;
        }


        event.preventDefault();


        closeMathDialog();

      }
    );


    // ===================================================
    // Formula answer: a single LaTeX expression, separate from rich segments.
    const formulaGroup = document.getElementById('formula-fields');
    if (formulaGroup) {
      const answer = formulaGroup.querySelector('[data-formula-answer-input]');
      const preview = formulaGroup.querySelector('[data-formula-answer-preview]');
      const previewField = formulaGroup.querySelector('[data-formula-answer-field]');
      const updatePreview = () => {
        const latex = String(answer.value || '').trim();
        preview.hidden = !latex;
        previewField.textContent = latex;
        if (customElements.get('math-field')) previewField.value = latex;
      };
      answer.addEventListener('input', updatePreview);
      formulaGroup.querySelector('[data-formula-answer-open]').addEventListener('click', () => {
        formulaAnswerTarget = formulaGroup;
        activeEditor = null;
        editingMathNode = null;
        mathField.value = answer.value || '';
        showMathDialog();
      });
      updatePreview();
      customElements.whenDefined('math-field').then(updatePreview);
    }

    // FINAL SYNC BEFORE POST
    // ===================================================

    const forms =
      new Set();


    document
      .querySelectorAll(
        "[data-rich-editor]"
      )
      .forEach(
        (editor) => {

          const form =
            editor.closest(
              "form"
            );


          if (form) {
            forms.add(
              form
            );
          }

        }
      );


    forms.forEach(
      (form) => {

        form.addEventListener(
          "submit",
          () => {

            form
              .querySelectorAll(
                "[data-rich-editor]"
              )
              .forEach(
                (editor) => {

                  syncEditor(
                    editor
                  );

                }
              );

          }
        );

      }
    );

  }
);