import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { Drawer } from '../Drawer';

function DrawerHarness() {
  const [isOpen, setIsOpen] = useState(false);
  const [updateCount, setUpdateCount] = useState(0);

  return (
    <UiLanguageProvider>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-expanded={isOpen}
        aria-controls="drawer-test"
      >
        打开操作
      </button>
      <Drawer isOpen={isOpen} onClose={() => setIsOpen(false)} title="操作详情" dialogId="drawer-test">
        <button type="button" onClick={() => setUpdateCount((count) => count + 1)}>
          更新内容 {updateCount}
        </button>
        <button type="button">最后一个操作</button>
      </Drawer>
    </UiLanguageProvider>
  );
}

describe('Drawer', () => {
  it('moves focus into the dialog, traps Tab, and restores focus after closing', () => {
    render(<DrawerHarness />);

    const opener = screen.getByRole('button', { name: '打开操作' });
    opener.focus();
    fireEvent.click(opener);

    const closeButton = screen.getByRole('button', { name: /关闭抽屉|Close drawer/ });
    const lastAction = screen.getByRole('button', { name: '最后一个操作' });
    expect(screen.getByRole('dialog')).toHaveAttribute('id', 'drawer-test');
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(lastAction).toHaveFocus();

    lastAction.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('keeps focus in place when the parent rerenders with a new close callback', () => {
    render(<DrawerHarness />);

    fireEvent.click(screen.getByRole('button', { name: '打开操作' }));
    const updateButton = screen.getByRole('button', { name: '更新内容 0' });
    updateButton.focus();
    fireEvent.click(updateButton);

    expect(screen.getByRole('button', { name: '更新内容 1' })).toHaveFocus();
  });
});
