"""Точка входа для PyInstaller."""
import multiprocessing

if __name__ == "__main__":
    # Обязательно первой строкой: на macOS служебные процессы multiprocessing (resource_tracker,
    # который заводят tqdm/huggingface_hub) перезапускают этот же исполняемый файл — без этого
    # вызова вместо служебного процесса стартовала бы вторая копия программы.
    multiprocessing.freeze_support()

    from voicetyper.__main__ import main

    main()
