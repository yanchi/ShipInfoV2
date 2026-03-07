<?php

namespace App\Enum;

enum ScraperStatusEnum: string
{
    case Running = 'running';
    case Success = 'success';
    case Partial = 'partial';
    case Failed  = 'failed';
}
